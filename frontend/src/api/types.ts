/**
 * types.ts — friendly names for the API's data shapes.
 *
 * Every type here comes from `schema.d.ts`, which is GENERATED from the backend's Pydantic models
 * (`npm run gen:api`). So if the backend changes a field, regenerating makes TypeScript point at every
 * place in the frontend that needs updating. The two apps can't silently drift apart.
 */
import type { components } from './schema';

type S = components['schemas'];

export type User = S['UserOut'];
export type UrlPreview = S['UrlPreviewOut'];
export type WatchSummary = S['WatchSummary'];
export type WatchDetail = S['WatchDetail'];
export type WatchCreate = S['WatchCreate'];
export type WatchPatch = S['WatchPatch'];
export type VolatileRule = S['VolatileRule'];
export type SnapshotItem = S['SnapshotItem'];
export type SnapshotDetail = S['SnapshotDetail'];
export type CompareResult = S['CompareResult'];
export type DiffOp = S['DiffOp'];
export type Region = S['Region'];
export type CheckLogItem = S['CheckLogItem'];
export type NumbersOut = S['NumbersOut'];
export type ActivityItem = S['ActivityItem'];
export type OverviewStats = S['OverviewStats'];
export type AdminStats = S['AdminStats'];
export type CheckQueued = S['CheckQueued'];
export type UserSettings = S['SettingsOut'];
export type SettingsUpdate = S['SettingsIn'];
export type TestAlertResult = S['TestAlertOut'];

export type Sensitivity = WatchDetail['sensitivity'];
export type KeywordMode = WatchDetail['keyword_mode'];

/** Live queue numbers pushed over SSE every 3 s (drives the Movement). */
export interface QueueStats {
  running: number;
  waiting: number;
  workers: number;
  workers_busy: boolean[];
  completed: number;
}
