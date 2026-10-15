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
