export interface VhcTeam {
  pk: number;
  name: string;
  code: string;
  color: string;
  active: boolean;
}

export interface VhcShipment {
  pk: number;
  reference: string;
  status: string;
  status_text: string;
}

export interface VhcPallet {
  pk: number;
  shipment: number;
  number: number;
  display_name: string;
}

export interface VhcLocation {
  pk: number;
  name: string;
  pathstring?: string;
}
export interface VhcPartSummary {
  pk: number;
  name: string;
  description: string;
  IPN?: string | null;
  revision?: string | null;
  units?: string | null;
}

export interface VhcBoxItem {
  pk: number;
  part: number;
  part_detail: VhcPartSummary;
  stock_item: number;
  quantity: number;
}

export interface VhcBox {
  pk: number;
  box_number: string;
  contents: string;
  items: VhcBoxItem[];
  team: number;
  team_detail: VhcTeam;
  other_team_description: string;
  shipment: number | null;
  shipment_detail: VhcShipment | null;
  pallet: number | null;
  pallet_detail: VhcPallet | null;
  current_location: number | null;
  current_location_detail: VhcLocation | null;
  destination: number | null;
  destination_detail: VhcLocation | null;
  note: string;
  status: string;
  status_text: string;
  source: string;
  source_text: string;
  created: string;
  updated: string;
  created_by_name: string | null;
  updated_by_name: string | null;
  revision: number;
}

export interface VhcBoxEvent {
  pk: number;
  action: string;
  action_text: string;
  user_name: string | null;
  timestamp: string;
  from_location_detail: VhcLocation | null;
  to_location_detail: VhcLocation | null;
  notes: string;
}

export function apiResults<T>(data: any): T[] {
  if (Array.isArray(data)) {
    return data;
  }

  return data?.results ?? [];
}


export function locationLabel(location: VhcLocation | null | undefined) {
  return location?.pathstring || location?.name || '?';
}
