// @vitest-environment jsdom

import { cleanup, render, waitFor } from "@testing-library/react";
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FuelMapCanvas } from "./FuelMapCanvas";
import type { Station } from "./FuelMapExplorer";

const leaflet = vi.hoisted(() => {
  const mapInstance = {
    flyTo: vi.fn(),
    getZoom: vi.fn(() => 13),
    remove: vi.fn(),
  };
  const markers: Array<{
    addTo: ReturnType<typeof vi.fn>;
    on: ReturnType<typeof vi.fn>;
    remove: ReturnType<typeof vi.fn>;
    options: Record<string, unknown>;
    coordinates: [number, number];
  }> = [];
  const tileLayer = { addTo: vi.fn() };

  return {
    divIcon: vi.fn((options) => options),
    map: vi.fn(() => mapInstance),
    mapInstance,
    marker: vi.fn(
      (coordinates: [number, number], options: Record<string, unknown>) => {
        const marker = {
          addTo: vi.fn().mockReturnThis(),
          on: vi.fn().mockReturnThis(),
          remove: vi.fn(),
          options,
          coordinates,
        };
        markers.push(marker);
        return marker;
      },
    ),
    markers,
    tileLayer: vi.fn(() => tileLayer),
    tileLayerInstance: tileLayer,
  };
});

vi.mock("leaflet", () => ({
  divIcon: leaflet.divIcon,
  map: leaflet.map,
  marker: leaflet.marker,
  tileLayer: leaflet.tileLayer,
}));

const stations: Station[] = [
  {
    id: "station-one",
    name: "Station One",
    address: "One Street",
    city: "Christchurch",
    distance: 1.2,
    latitude: -43.53,
    longitude: 172.63,
    prices: { "91": 2.2, "95": 2.3, "98": 2.4, Diesel: 1.8 },
    observedAt: { "91": "2026-08-12T00:00:00Z" },
    contributors: {},
  },
  {
    id: "station-two",
    name: "Station One",
    address: "Two Street",
    city: "Christchurch",
    distance: 2.1,
    latitude: -43.54,
    longitude: 172.64,
    prices: { "91": 2.25, "95": 2.35, "98": 2.45, Diesel: 1.85 },
    observedAt: { "91": "2026-08-12T00:00:00Z" },
    contributors: {},
  },
];

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  leaflet.markers.length = 0;
  leaflet.mapInstance.getZoom.mockReturnValue(13);
});

describe("FuelMapCanvas", () => {
  it("initialises the map, tiles, and station price markers", async () => {
    render(
      <FuelMapCanvas
        fuel="91"
        stations={stations}
        selectedStation={stations[0]}
        userLocation={null}
        onSelect={vi.fn()}
      />,
    );

    await waitFor(() => expect(leaflet.map).toHaveBeenCalledOnce());
    expect(leaflet.tileLayer).toHaveBeenCalledWith(
      "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
      expect.objectContaining({ maxZoom: 19 }),
    );
    expect(leaflet.tileLayerInstance.addTo).toHaveBeenCalledWith(
      leaflet.mapInstance,
    );
    await waitFor(() => expect(leaflet.marker).toHaveBeenCalledTimes(2));
    expect(leaflet.divIcon).toHaveBeenCalledWith(
      expect.objectContaining({ html: expect.stringContaining("$2.200") }),
    );
    expect(leaflet.divIcon.mock.calls.filter(([options])=>String(options.html).includes(" selected")).length).toBe(1);
  });

  it("selects a station when its marker is activated", async () => {
    const onSelect = vi.fn();
    render(
      <FuelMapCanvas
        fuel="91"
        stations={stations}
        selectedStation={stations[0]}
        userLocation={null}
        onSelect={onSelect}
      />,
    );

    await waitFor(() => expect(leaflet.markers).toHaveLength(2));
    const clickHandler = leaflet.markers[1].on.mock.calls.find(
      ([event]) => event === "click",
    )?.[1] as (() => void) | undefined;
    expect(clickHandler).toBeTypeOf("function");
    clickHandler?.();
    expect(onSelect).toHaveBeenCalledWith("station-two");
  });

  it("moves marker selection between stations with the same name", async () => {
    const view=render(<FuelMapCanvas fuel="91" stations={stations} selectedStation={stations[0]} userLocation={null} onSelect={vi.fn()} />);
    await waitFor(()=>expect(leaflet.marker).toHaveBeenCalledTimes(2));
    expect(leaflet.divIcon.mock.calls.slice(-2).map(([options])=>String(options.html).includes(" selected"))).toEqual([true,false]);
    view.rerender(<FuelMapCanvas fuel="91" stations={stations} selectedStation={stations[1]} userLocation={null} onSelect={vi.fn()} />);
    await waitFor(()=>expect(leaflet.marker).toHaveBeenCalledTimes(4));
    expect(leaflet.divIcon.mock.calls.slice(-2).map(([options])=>String(options.html).includes(" selected"))).toEqual([false,true]);
  });

  it("adds and recentres on the user's location", async () => {
    render(
      <FuelMapCanvas
        fuel="91"
        stations={stations}
        selectedStation={stations[0]}
        userLocation={{ latitude: -43.51, longitude: 172.61 }}
        onSelect={vi.fn()}
      />,
    );

    await waitFor(() =>
      expect(leaflet.marker).toHaveBeenCalledWith(
        [-43.51, 172.61],
        expect.objectContaining({ title: "Your location" }),
      ),
    );
    expect(leaflet.mapInstance.flyTo).toHaveBeenCalledWith(
      [-43.51, 172.61],
      14,
      { duration: 0.8 },
    );
  });

  it("removes the Leaflet map on unmount", async () => {
    const view = render(
      <FuelMapCanvas
        fuel="91"
        stations={stations}
        selectedStation={stations[0]}
        userLocation={null}
        onSelect={vi.fn()}
      />,
    );
    await waitFor(() => expect(leaflet.map).toHaveBeenCalledOnce());

    view.unmount();

    expect(leaflet.mapInstance.remove).toHaveBeenCalledOnce();
  });
});
