// @vitest-environment jsdom

import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
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

function stationList() {
  const list = document.querySelector(".station-list");
  if (!list) throw new Error("Station list not found");
  return within(list as HTMLElement);
}

describe("FuelMapExplorer", () => {
  it("switches fuel type and updates visible prices", () => {
    render(<FuelMapExplorer />);

    fireEvent.click(screen.getByRole("radio", { name: "95" }));

    expect(screen.getByRole("heading", { name: "Nearby 95" })).toBeTruthy();
    expect(
      stationList().getByRole("button", { name: /NPD Moorhouse.*\$2\.399/ }),
    ).toBeTruthy();
  });

  it("sorts station rows by price or distance", () => {
    render(<FuelMapExplorer />);
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

  it("shows the selected station in the map detail", () => {
    render(<FuelMapExplorer />);

    fireEvent.click(
      stationList().getByRole("button", { name: /Mobil Papanui/ }),
    );

    expect(document.querySelector(".map-detail")?.textContent).toContain(
      "Mobil Papanui",
    );
  });

  it("confirms that the map uses a successful location", () => {
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

    fireEvent.click(screen.getByRole("button", { name: /Use my location/ }));

    expect(screen.getByRole("status").textContent).toContain(
      "Your current location is marked on the map",
    );
  });

  it("falls back to the preview when geolocation fails", () => {
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

    fireEvent.click(screen.getByRole("button", { name: /Use my location/ }));

    expect(screen.getByRole("status").textContent).toContain(
      "Location is unavailable",
    );
  });
});
