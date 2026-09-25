import { lazy, Suspense } from "react";
import type { RouteObject } from "react-router";
import { AppShell } from "./components/layout/AppShell";
import { SkeletonRows } from "./components/States";

const Overview = lazy(() => import("./pages/Overview"));
const LiveMap = lazy(() => import("./pages/LiveMap"));
const Stations = lazy(() => import("./pages/Stations"));
const StationDetail = lazy(() => import("./pages/StationDetail"));
const Predictions = lazy(() => import("./pages/Predictions"));
const Alerts = lazy(() => import("./pages/Alerts"));
const DataStatus = lazy(() => import("./pages/DataStatus"));
const NotFound = lazy(() => import("./pages/NotFound"));

const page = (el: React.ReactNode) => <Suspense fallback={<div className="pt-6"><SkeletonRows label="Loading page" /></div>}>{el}</Suspense>;

export const routes: RouteObject[] = [
  {
    element: <AppShell />,
    children: [
      { index: true, element: page(<Overview />) },
      { path: "map", element: page(<LiveMap />) },
      { path: "stations", element: page(<Stations />) },
      { path: "stations/:stationId", element: page(<StationDetail />) },
      { path: "predictions", element: page(<Predictions />) },
      { path: "alerts", element: page(<Alerts />) },
      { path: "status", element: page(<DataStatus />) },
      { path: "*", element: page(<NotFound />) },
    ],
  },
];


