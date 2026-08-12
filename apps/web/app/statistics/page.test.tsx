// @vitest-environment jsdom

import { cleanup, render, screen } from "@testing-library/react";
import React from "react";
import { afterEach, expect, it, vi } from "vitest";
vi.mock("../components/SiteChrome",()=>({SiteHeader:()=> <header>Header</header>,SiteFooter:()=> <footer>Footer</footer>}));
import StatisticsPage from "./page";

afterEach(() => { cleanup();vi.restoreAllMocks(); });

it("renders live aggregate statistics and current cheapest stations", async () => {
  vi.stubGlobal("fetch",vi.fn().mockResolvedValue({ok:true,json:async()=>({generated_at:"2026-08-12T00:00:00Z",priced_station_count:2,reports_week:7,averages:[{fuel_type:"PETROL_91",average_price:2.45,station_count:2}],stations:[{id:"one",name:"Lower Fuel",city:"Auckland",prices:{PETROL_91:2.4}},{id:"two",name:"Higher Fuel",city:"Wellington",prices:{PETROL_91:2.5}}]})}));
  render(<StatisticsPage />);
  expect(screen.getByRole("status").textContent).toContain("Loading");
  expect(await screen.findByText("Lower Fuel")).toBeTruthy();
  expect(document.querySelector(".average-value")?.textContent).toContain("$2.450/L");
  expect(screen.getByText("7")).toBeTruthy();
  expect(document.body.textContent).not.toContain("Illustrative");
});

it("shows an error when statistics cannot be loaded", async () => {
  vi.stubGlobal("fetch",vi.fn().mockResolvedValue({ok:false}));
  render(<StatisticsPage />);
  expect((await screen.findByRole("alert")).textContent).toContain("could not be loaded");
});
