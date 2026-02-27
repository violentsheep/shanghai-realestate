export interface DayRecord {
  date: string;
  scraped_at: string;
  second_hand: {
    units: number | null;
    area: number | null;
    avg_area: number | null;
    note: string;
  };
  new_house: {
    units: number | null;
    area: number | null;
    avg_area: number | null;
    note: string;
  };
  listing: {
    total: number | null;
    note: string;
  };
}
