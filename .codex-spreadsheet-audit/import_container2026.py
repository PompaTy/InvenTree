#!/usr/bin/env python3
"""Import the normalized Container 2026 staging data into InvenTree."""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from datetime import date
from decimal import Decimal
from pathlib import Path


BASE_DIR = Path("/home/inventree")
BACKEND_DIR = BASE_DIR / "src/backend/InvenTree"
AUDIT_DIR = BASE_DIR / ".codex-spreadsheet-audit"
STAGING_PATH = AUDIT_DIR / "container2026-staging.json"
RESULT_PATH = AUDIT_DIR / "container2026-import-result.json"
FAILURE_PATH = AUDIT_DIR / "container2026-import-failure.json"

sys.path.insert(0, str(BACKEND_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "InvenTree.settings")

import django  # noqa: E402

django.setup()

from django.contrib.auth import get_user_model  # noqa: E402
from django.db import connection, transaction  # noqa: E402

from part.models import Part  # noqa: E402
from stock.models import StockItem, StockLocation  # noqa: E402
from vhc.models import (  # noqa: E402
    Box,
    BoxEvent,
    BoxEventAction,
    BoxItem,
    BoxSequence,
    BoxSource,
    BoxStatus,
    Shipment,
    Team,
)


TEAM_COLORS = [
    "#228BE6",
    "#12B886",
    "#FA5252",
    "#7950F2",
    "#F59F00",
    "#15AABF",
    "#E64980",
    "#5C940D",
    "#868E96",
]


def load_staging() -> dict:
    with STAGING_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def team_code(name: str, used_codes: set[str]) -> str:
    code = "".join(char if char.isalnum() else "_" for char in name.upper())
    code = "_".join(part for part in code.split("_") if part) or "UNASSIGNED"
    code = code[:30]
    base = code
    suffix = 2
    while code in used_codes:
        marker = f"_{suffix}"
        code = f"{base[: 30 - len(marker)]}{marker}"
        suffix += 1
    used_codes.add(code)
    return code


def preflight(data: dict) -> dict:
    boxes = data["boxes"]
    box_numbers = [box["box_number"] for box in boxes]
    if len(box_numbers) != len(set(box_numbers)):
        raise RuntimeError("Staging data contains duplicate box numbers")
    if any(len(number) != 6 or not number.isdigit() for number in box_numbers):
        raise RuntimeError("Staging data contains an invalid box number")
    if any(not box["items"] for box in boxes):
        raise RuntimeError("Staging data contains an empty box")

    part_definitions: dict[str, tuple[str, str]] = {}
    source_rows: list[int] = []
    for box in boxes:
        for item in box["items"]:
            if Decimal(str(item["quantity"])) <= 0:
                raise RuntimeError(
                    f"Non-positive quantity in box {box['box_number']}"
                )
            signature = (item["part_key"], item["name"])
            existing = part_definitions.setdefault(item["ipn"], signature)
            if existing != signature:
                raise RuntimeError(f"Conflicting definition for IPN {item['ipn']}")
            source_rows.extend(item["source_rows"])

    skipped_rows = [row["row"] for row in data["skipped_rows"]]
    if len(source_rows) != len(set(source_rows)):
        raise RuntimeError("A spreadsheet source row is imported more than once")
    if len(source_rows) + len(skipped_rows) != 579:
        raise RuntimeError("Spreadsheet row accounting does not equal 579 item rows")

    return {
        "boxes": len(boxes),
        "box_items": sum(len(box["items"]) for box in boxes),
        "parts": len(part_definitions),
        "imported_source_rows": len(source_rows),
        "skipped_source_rows": len(skipped_rows),
        "total_quantity": str(
            sum(
                Decimal(str(item["quantity"]))
                for box in boxes
                for item in box["items"]
            )
        ),
    }


def get_or_create_location(name: str) -> StockLocation:
    location = StockLocation.objects.filter(name=name, parent=None).first()
    if location is None:
        location = StockLocation(name=name)
        location.save()
    return location


@transaction.atomic
def apply_import(data: dict, dry_run_summary: dict) -> dict:
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [20260730])

    existing = {
        "parts": Part.objects.count(),
        "stock_items": StockItem.objects.count(),
        "boxes": Box.objects.count(),
    }
    if any(existing.values()):
        raise RuntimeError(
            "Inventory is no longer empty; import aborted to prevent duplicates: "
            f"{existing}"
        )

    user_model = get_user_model()
    import_user = user_model.objects.filter(username="admin", is_active=True).first()
    if import_user is None:
        import_user = user_model.objects.filter(is_superuser=True, is_active=True).first()
    if import_user is None:
        raise RuntimeError("No active administrator account is available for audit records")

    team_names = sorted({box["team"] for box in data["boxes"]})
    used_codes = set(Team.objects.values_list("code", flat=True))
    teams: dict[str, Team] = {}
    for index, name in enumerate(team_names):
        team = Team.objects.filter(name=name).first()
        if team is None:
            team = Team.objects.create(
                name=name,
                code=team_code(name, used_codes),
                color=TEAM_COLORS[index % len(TEAM_COLORS)],
                active=True,
                display_order=index,
            )
        teams[name] = team

    location_names = {"VA Warehouse"}
    for box in data["boxes"]:
        location_names.add(box["current_location"])
        if box["destination"]:
            location_names.add(box["destination"])
    locations = {
        name: get_or_create_location(name) for name in sorted(location_names)
    }

    shipment_data = data["shipment"]
    shipment, _ = Shipment.objects.update_or_create(
        reference=shipment_data["reference"],
        defaults={
            "year": shipment_data["year"],
            "kind": shipment_data["kind"],
            "status": shipment_data["status"],
            "notes": shipment_data["notes"],
        },
    )

    part_definitions: dict[str, dict] = {}
    for box in data["boxes"]:
        for item in box["items"]:
            part_definitions.setdefault(item["ipn"], item)

    parts: dict[str, Part] = {}
    for ipn, item in sorted(part_definitions.items()):
        part = Part(
            name=item["name"],
            description="Imported from Container 2026 spreadsheet",
            IPN=ipn,
            creation_user=import_user,
        )
        part.save()
        parts[ipn] = part

    created_boxes: list[str] = []
    expired_items: list[dict] = []
    for box_data in data["boxes"]:
        box = Box.objects.create(
            box_number=box_data["box_number"],
            team=teams[box_data["team"]],
            shipment=shipment,
            current_location=locations[box_data["current_location"]],
            destination=(
                locations[box_data["destination"]]
                if box_data["destination"]
                else None
            ),
            note=box_data["note"],
            status=BoxStatus.PACKED,
            source=BoxSource.DONATION_PURCHASE,
            created_by=import_user,
            updated_by=import_user,
            revision=1,
        )

        summary_parts: list[str] = []
        for item_data in box_data["items"]:
            quantity = Decimal(str(item_data["quantity"]))
            expiry_date = (
                date.fromisoformat(item_data["expiry_date"])
                if item_data["expiry_date"]
                else None
            )
            stock_note = (
                f"Imported from Inventory for Container (2026)-3.xlsx; "
                f"assigned to VHC box {box.box_number}"
            )
            stock_item = StockItem(
                part=parts[item_data["ipn"]],
                quantity=quantity,
                location=box.current_location,
                size=item_data["size"],
                sterile=item_data["sterile"],
                expiry_date=expiry_date,
            )
            stock_item.save(user=import_user, notes=stock_note)
            BoxItem.objects.create(
                box=box,
                part=parts[item_data["ipn"]],
                stock_item=stock_item,
                quantity=quantity,
                size=item_data["size"],
                sterile=item_data["sterile"],
                expiry_date=expiry_date,
            )
            summary_parts.append(f"{item_data['name']} ({quantity:g})")
            if expiry_date and expiry_date < date.today():
                expired_items.append(
                    {
                        "box_number": box.box_number,
                        "part": item_data["name"],
                        "quantity": str(quantity),
                        "expiry_date": expiry_date.isoformat(),
                    }
                )

        box.contents = ", ".join(summary_parts)[:500]
        box.save(update_fields=["contents", "updated"])
        BoxEvent.objects.create(
            box=box,
            action=BoxEventAction.CREATED,
            user=import_user,
            to_location=box.current_location,
            notes="Imported from Container 2026 workbook",
            changes={
                "source_rows": [
                    row
                    for item in box_data["items"]
                    for row in item["source_rows"]
                ],
                "items": box.contents,
            },
        )
        created_boxes.append(box.box_number)

    BoxSequence.objects.update_or_create(year=2026, defaults={"next_value": 167})

    result = {
        "status": "complete",
        "source_file": data["source_file"],
        "shipment": shipment.reference,
        "import_user": import_user.username,
        "expected": dry_run_summary,
        "database": {
            "users": user_model.objects.count(),
            "teams": Team.objects.count(),
            "locations": StockLocation.objects.count(),
            "parts": Part.objects.count(),
            "boxes": Box.objects.count(),
            "box_items": BoxItem.objects.count(),
            "stock_items": StockItem.objects.count(),
            "box_events": BoxEvent.objects.count(),
            "shipments": Shipment.objects.count(),
            "stock_quantity": str(
                sum(StockItem.objects.values_list("quantity", flat=True), Decimal("0"))
            ),
        },
        "created_boxes": created_boxes,
        "skipped_rows": data["skipped_rows"],
        "skipped_boxes": data["skipped_boxes"],
        "normalization_warnings": data["warnings"],
        "expired_items": expired_items,
    }
    return result


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Commit the import. Without this flag, only validate staging data.",
    )
    args = parser.parse_args()

    data = load_staging()
    summary = preflight(data)
    print(json.dumps({"status": "validated", **summary}), flush=True)
    if not args.apply:
        return 0

    result = apply_import(data, summary)
    write_json(RESULT_PATH, result)
    if FAILURE_PATH.exists():
        FAILURE_PATH.unlink()
    print(json.dumps(result["database"]), flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BaseException as exc:
        failure = {
            "status": "failed",
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }
        write_json(FAILURE_PATH, failure)
        raise
