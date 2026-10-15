# Design system: haute horlogerie for the web

ChangeWatch watches web pages, so the interface borrows from fine watchmaking. Each page a user
monitors becomes its own watch dial, engraved with a pattern generated from its address, much like a
serial-numbered timepiece. The rest of the interface is deliberately quiet. All the boldness goes into
the dials; everything else is hairlines, generous space and careful alignment, like a watch catalogue.

## 1. Vocabulary, and where each idea appears

| Watchmaking term | What it is | Where it appears in ChangeWatch |
|---|---|---|
| Guilloché | Engine-turned engraving of interlocking curves on a dial | The pattern on every dial, generated from the page's URL (`components/dial/guilloche.ts`) |
| Fumé | Smoked enamel that darkens toward the edge | The dark theme's radial background |
| Opaline | Matte silvered dial finish | The light theme |
| Heat-blued steel | Steel heated until it turns deep blue | The sweep hand, links, focus rings |
| Ruby jewels | Synthetic rubies used as bearings | Status jewels, pivots in the Movement |
| Lume | Luminous paint on hands and markers | "OK", "running", added text |
| Côtes de Genève | Striped finish on movement plates | The Movement plate behind the gear train |
| Date window | A small aperture showing the date | Time since the page last changed |
| Loupe | A watchmaker's magnifier | The magnifier on the screenshot diff |

## 2. Palette

Two themes. Both are CSS variables in `frontend/src/design/tokens.css`. Fumé is set on `:root` and
Opaline on `[data-theme="opaline"]`.

### Fumé (default, dark)
| Token | Value | Role |
|---|---|---|
| `--fume-center` | `#17392F` | centre of the radial page background |
| `--fume-edge` | `#060A09` | edge of the background |
| `--surface` | `#0E1714` | panels |
| `--surface-raised` | `#13201C` | menus, modals |
| `--text` (opaline) | `#ECE7DC` | primary text |
| `--text-2` (rhodium) | `#A9B2AE` | secondary text, rings, ticks |
| `--hairline` | `rgba(236,231,220,.10)` | dividers |
| `--accent` (salmon) | `#EFA98C` | primary actions (text `#0B1411`), engraving, "changed" |
| `--blued` | `#5B78F6` | hands, links, focus ring |
| `--lume` | `#BFF7D8` | OK, live, added text |
| `--ruby` | `#F0607F` | errors, removed text |
| `--topaz` | `#F4B860` | blocked, warnings |
| `--moonstone` | `#9FB4C7` | pending |

### Opaline (light)
| Token | Value | Role |
|---|---|---|
| `--bg` | `#E9EAE6` | page (cool silver, not cream) |
| `--surface` / raised | `#F4F4F1` / `#FFFFFF` | panels |
| `--text` / `--text-2` | `#141917` / `#4F5754` | text |
| `--hairline` | `rgba(20,25,23,.12)` | dividers |
| `--accent` (blued) | `#2340C8` | primary actions (white text), engraving, hands, links |
| `--salmon` | `#C8694A` | "changed" highlights |
| `--lume` | `#1D8A5B` | OK, added |
| `--ruby` | `#B8163F` | errors, removed |
| `--topaz` | `#A86A00` | blocked |
| `--moonstone` | `#5E7A93` | pending |

**Status mapping, both themes:** OK uses lume, error ruby, blocked topaz, pending moonstone and paused
the secondary text colour. Colour never carries status alone; a jewel always appears with a word.

**Contrast:** every text colour above passes WCAG AA (4.5:1) on its own theme's surface. The
semantic colours used as text in Opaline were darkened for exactly this reason: lume `#1D8A5B` and
topaz `#A86A00`.

## 3. Typography
- **Zodiak** (display, weights 300 and 400, never bold) is a high-contrast serif with engraved-feeling
  details. It's used for page titles, dial readouts and big numbers.
- **Switzer** (text and UI) is a Swiss-style grotesk; the name is the point: Swiss made.
- **JetBrains Mono** appears only inside diff views, where columns must line up.
- All three are self-hosted in `src/assets/fonts/`, so the app never depends on a font CDN.
- The type scale in px is 12, 14, 16, 18, 21, 24, 32, 44, 60 and 84. Body text is 16/1.55. Page
  titles are Zodiak 44 (60 on wide screens), section titles Zodiak 32, and the landing headline
  Zodiak 84 (44 on mobile).
- All copy is in sentence case. Prose is capped at 68 characters per line. Numbers use
  `tabular-nums lining-nums` so live counters don't jitter.

## 4. Materials (pure CSS/SVG, no image files)
- **Grain:** an SVG `feTurbulence` noise layer at about 3% opacity sits over the whole page, so the
  radial gradient never shows bands.
- **Sunburst brushing:** a `repeating-conic-gradient` of fine rays under each dial's engraving.
- **Specular highlight:** a soft radial light on each dial that follows the pointer through the
  `--mx`/`--my` CSS variables. It appears only on dials and the landing hero.
- **Côtes de Genève:** a `repeating-linear-gradient` at 115° on the Movement plate.
- **Depth:** raised surfaces get a dark tinted shadow plus a 1 px inner highlight on the top edge,
  like a polished bevel. There are no generic grey drop shadows.
- **Radii:** dials are circles, panels 20 px, inputs 12 px, primary buttons fully rounded (like a
  crown), chips 8 px.

## 5. Layout
- Content is left-aligned on a 1200 px max-width container with 24 px gutters (16 px on phones).
- Sections are separated by hairline rules and space, not by boxes. Cards are used sparingly.
- The dashboard grid is `repeat(auto-fill, minmax(180px, 1fr))` with plenty of air around each dial.
- Every layout works down to 360 px wide with no horizontal scroll.

## 6. Motion: motion explains state
| Token | Value |
|---|---|
| `--ease-out` | `cubic-bezier(.22,1,.36,1)` |
| `--ease-mech` | `cubic-bezier(.65,0,.35,1)` |
| durations | 160 ms (hover/press), 280 ms (UI state), 600 ms (routes), 900 ms (orchestrated load) |
| springs | stiffness 300, damping 30 (loupe, tilt) |

- **One orchestrated moment per page load.** On the dashboard, dials wind into place and their
  guilloché engraves in.
- **Live motion means something.** The sweep hand shows real progress to the next check, the Movement
  turns only while checks run, and a dial re-engraves once when its page changes.
- **Not used:** fade-and-slide on every section, hover-lift everywhere, parallax, bouncing, or looping
  animations that compete for attention.
- **Reduced motion:** with `prefers-reduced-motion: reduce`, hands jump into position and update every
  30 s, engraving appears instantly, tilt is off, and transitions become fades of 120 ms or less.

## 7. Writing
Copy uses plain words, sentence case and the active voice. Things are named the way users think of
them: Pages, Add page, Activity, Settings, Check now, Compare versions, Pick regions. Errors say what
happened and what happens next. The UI never uses exclamation marks, emoji or "Oops".

## 8. Things we deliberately avoid
- Identical rounded cards in a grid, each with the same soft grey shadow
- ALL-CAPS letter-spaced labels; " · " metadata joins; "→" on buttons; fake 01/02/03 numbering
- Cream with terracotta; black with one neon; glassmorphism; gradient text; purple "AI" gradients
- Emoji, stock illustrations, anything that looks like a component library

## 9. Quality floor
- WCAG AA contrast, full keyboard navigation, and a visible focus ring (2 px blued plus a soft glow)
- Touch targets of at least 44 px
- A dashboard with 30 dials stays smooth. Guilloché paths are cached, off-screen dials use
  `content-visibility: auto`, and only transform, opacity and stroke-dashoffset are animated.
- Every screen is reviewed in screenshots at 1440×900 and 390×844 in both themes.
