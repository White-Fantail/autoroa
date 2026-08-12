// @vitest-environment jsdom

import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FuelMapExplorer } from "./FuelMapExplorer";

vi.mock("./FuelMapCanvas", () => ({
  FuelMapCanvas: ({
    fuel,
    selectedStation,
  }: {
    fuel: string;
    selectedStation: { name: string };
  }) => (
    <div role="region" aria-label={`Interactive map showing ${fuel} fuel prices`}>
      <div className="map-detail">{selectedStation.name}</div>
    </div>
  ),
}));

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const snapshot={stations:[
  {id:"npd",name:"NPD Moorhouse",address:"Moorhouse Avenue",city:"Christchurch",latitude:-43.53943,longitude:172.63122,prices:{PETROL_91:2.239,PETROL_95:2.399,PETROL_98:2.489,DIESEL:1.739},observed_at:{PETROL_91:"2026-08-10T00:00:00Z",PETROL_95:"2026-08-12T00:00:00Z"}},
  {id:"waitomo",name:"Waitomo Fitzgerald",address:"Fitzgerald Avenue",city:"Christchurch",latitude:-43.53215,longitude:172.64668,prices:{PETROL_91:2.259,PETROL_95:2.419,PETROL_98:2.519,DIESEL:1.759},observed_at:{PETROL_91:"2026-08-12T00:00:00Z"}},
  {id:"mobil",name:"Mobil Papanui",address:"Papanui Road",city:"Christchurch",latitude:-43.50353,longitude:172.61215,prices:{PETROL_91:2.309,PETROL_95:2.469,PETROL_98:2.559,DIESEL:1.809},observed_at:{PETROL_91:"2026-08-12T00:00:00Z"}},
]};
beforeEach(()=>{vi.stubGlobal("fetch",vi.fn().mockResolvedValue({ok:true,json:async()=>snapshot}))});

function stationList() {
  const list = document.querySelector(".station-list");
  if (!list) throw new Error("Station list not found");
  return within(list as HTMLElement);
}

describe("FuelMapExplorer", () => {
  it("switches fuel type and updates visible prices", async () => {
    render(<FuelMapExplorer />);
    await screen.findAllByText("NPD Moorhouse");

    fireEvent.click(screen.getByRole("radio", { name: "95" }));

    expect(screen.getByRole("heading", { name: "Nearby 95" })).toBeTruthy();
    expect(
      stationList().getByRole("button", { name: /NPD Moorhouse.*\$2\.399/ }),
    ).toBeTruthy();
    const row=stationList().getByRole("button", { name: /NPD Moorhouse/ });
    expect(row.textContent).toContain("Updated 10 hr ago");
    fireEvent.click(screen.getByRole("radio", { name: "91" }));
    expect(row.textContent).toContain("Updated 2 days ago");
  });

  it("sorts station rows by price or distance", async () => {
    render(<FuelMapExplorer />);
    await screen.findAllByText("NPD Moorhouse");
    const list = stationList();

    expect(list.getAllByRole("button")[0].textContent).toContain(
      "NPD Moorhouse",
    );
    fireEvent.change(screen.getByLabelText("Sort stations"), {
      target: { value: "distance" },
    });
    expect(list.getAllByRole("button")[0].textContent).toContain(
      "Waitomo Fitzgerald",
    );
  });

  it("shows the selected station in the map detail", async () => {
    render(<FuelMapExplorer />);
    await screen.findAllByText("NPD Moorhouse");

    fireEvent.click(
      stationList().getByRole("button", { name: /Mobil Papanui/ }),
    );

    expect(document.querySelector(".map-detail")?.textContent).toContain(
      "Mobil Papanui",
    );
  });

  it("selects duplicate station names by their unique ID", async () => {
    const duplicate={...snapshot.stations[0],id:"npd-two",address:"Second address",prices:{...snapshot.stations[0].prices,PETROL_91:2.1}};
    vi.mocked(fetch).mockResolvedValueOnce({ok:true,json:async()=>({stations:[...snapshot.stations,duplicate]})} as Response);
    render(<FuelMapExplorer />);await screen.findAllByText("NPD Moorhouse");
    fireEvent.click(stationList().getByRole("button",{name:/Second address/}));
    expect(stationList().getByRole("button",{name:/Second address/}).className).toContain("selected");
    expect(stationList().getByRole("button",{name:/Moorhouse Avenue/}).className).not.toContain("selected");
  });

  it("confirms that the map uses a successful location", async () => {
    Object.defineProperty(navigator, "geolocation", {
      configurable: true,
      value: {
        getCurrentPosition: vi.fn((success: PositionCallback) =>
          success({
            coords: { latitude: -43.53, longitude: 172.63 },
          } as GeolocationPosition),
        ),
      },
    });
    render(<FuelMapExplorer />);
    await screen.findAllByText("NPD Moorhouse");

    fireEvent.click(screen.getByRole("button", { name: /Use my location/ }));

    expect(screen.getByRole("status").textContent).toContain(
      "Your current location is marked on the map",
    );
  });

  it("falls back to the preview when geolocation fails", async () => {
    Object.defineProperty(navigator, "geolocation", {
      configurable: true,
      value: {
        getCurrentPosition: vi.fn(
          (_success: PositionCallback, failure: PositionErrorCallback) =>
            failure({} as GeolocationPositionError),
        ),
      },
    });
    render(<FuelMapExplorer />);
    await screen.findAllByText("NPD Moorhouse");

    fireEvent.click(screen.getByRole("button", { name: /Use my location/ }));

    expect(screen.getByRole("status").textContent).toContain(
      "Location is unavailable",
    );
  });

  it("shows a recoverable error when current prices cannot be loaded", async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ok:false} as Response);
    render(<FuelMapExplorer />);
    expect((await screen.findByRole("alert")).textContent).toContain("could not be loaded");
    expect(screen.queryByText("NPD Moorhouse")).toBeNull();
  });
});
