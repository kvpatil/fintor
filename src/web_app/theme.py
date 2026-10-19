"""Theme CSS.

Tabular numerals are the point of this file. Financial figures that shift
horizontally as values update read as sloppy, and proportional digits are the
single most common tell that a dashboard was not built by someone who looks at
numbers for a living. One CSS line fixes it everywhere.
"""

from __future__ import annotations

import streamlit as st

CSS = """
<style>
:root {
  --fin-ink: #1a1820;
  /* Darkened from #5f6b66: 5.3:1 -> 6.3:1 on the light ground. Size was the real
     legibility problem, but at 14px the extra presence costs nothing. */
  --fin-muted: #585461;
  --fin-line: #d9d6e0;
  --fin-accent: #521fcd;
  --fin-warn: #9a6a1b;
  /* Card/chip ground. A token because it was hardcoded #fdfdfd in five rules,
     every one of which would have stayed light-on-dark. */
  --fin-paper: #fdfdfd;
  /* Ground for the "What this shows" panel: a tint of the page, not a new hue. */
  --fin-note-ground: #eeedf1;
  /* Card ground on the sign-in screen. The six accounts are a wall of small
     text on white; a tint of the brand hue gives the eye an edge to rest on
     without introducing a second colour. Measured on this ground, not assumed:
     ink 15.53:1, muted 6.50:1, accent 7.62:1. */
  --fin-card-tint: #f3effc;
  /* The tagline under the wordmark. Deliberately ONE value for both themes,
     and deliberately not redefined in the dark block - it has to equal
     brand.MARK_RIB, the leaf's stem, and that is baked into a themeless <img>
     that cannot follow the viewer. Measured on both grounds: 3.11:1 light,
     5.66:1 dark. AA for LARGE text, which the tagline is at 1.9rem/700; it
     would fail at body size, so this token stays on the tagline.
     tests/test_brand.py fails the build if it drifts from MARK_RIB. */
  --fin-tagline: #9b7aeb;
  /* Border for a text field. NOT --fin-line: that is a page hairline, and
     measured against a field fill it is 1.23:1 light and 1.29:1 dark - far
     under the 3:1 WCAG asks of a control boundary (1.4.11), which is why the
     dark inputs were invisible. Streamlit paints the field's border in the
     SAME colour as its fill, and in dark that fill also equals the card, so
     there was neither an edge nor a change of ground to see.
     #837e92: 3.36:1 on the fill, 3.85:1 on the card. */
  --fin-field-line: #837e92;
  /* Direction of a price move. Reserved status colours - never a series hue. */
  --fin-up: #1b7f4e;
  --fin-down: #b4332f;

  /* Type scale. These exist because the small sizes drifted down to 11.5px by
     being hand-picked one rule at a time. Nothing goes below --fs-xs, and
     tests/test_theme.py fails the build if a raw literal sneaks under it. */
  --fs-xs: 0.875rem;    /* 14px - chips, uppercase eyebrows */
  --fs-sm: 0.9375rem;   /* 15px - secondary text, breadcrumb, identity */
  --fs-md: 1rem;        /* 16px - body */

  /* Navigation colour, in two layers. Layer one: a tint saying what KIND of page
     a tab is - workspace you operate, reference you consult. Layer two: a dot
     saying what the system is doing, painted from DataStatus and the budget.
     The dot variables are overwritten per rerun by chrome.nav_state_style().

     The dots are SEMANTIC and deliberately not the brand colour: green means
     live, grey means cached, amber means look at this. They are the same green
     as --fin-up, because one app should have one green that means "good".
     When the brand was green these collided with it; violet separates them. */
  --tab-workspace: rgba(82, 31, 205, 0.08);
  --tab-reference: rgba(90, 104, 120, 0.10);
  /* Hover was hardcoded rgba(31,111,92,0.16) and so stayed a light-mode green
     on the dark ground. A token because every other nav colour is one. */
  --tab-hover: rgba(82, 31, 205, 0.16);
  --dot-live: #1b7f4e;
  --dot-cached: #8a948f;
  --dot-attention: #c07c12;
  --dot-market: transparent;
  --dot-portfolio: transparent;
  --dot-internals: transparent;

  /* Content measure. Without this the app is full-bleed: at 1500px the prompt
     buttons stretch ~1370px and running prose hits an unreadable measure. The
     .gate-wrap max-width that was supposed to do this never applied, because
     Streamlit renders its columns outside any wrapper div we emit. */
  --fin-measure: 1120px;
  /* The gate is a 3-up card grid, not running prose, so it does not want a
     reading measure at all. 1280px left ~160px of dead gutter either side on a
     1600px viewport; min() keeps a margin on smaller screens instead of
     clamping to a width they do not have. gate.render() swaps to this. */
  --fin-measure-gate: min(98vw, 1800px);
  --fin-prose: 72ch;

  /* Distance from the top of the viewport to the first thing on the page.
     Streamlit's top nav is a FIXED 60px header that overlays the content - the
     main container starts at y=0 behind it - so this has to clear 60px before it
     buys any visible air. Measured in the browser: 3.5rem leaves the header row
     12px clear of the nav. Below 3rem the Switch button is clipped. */
  --fin-top-gap: 3.5rem;

  /* The gate's mark height, and the distance from the top of the brand panel
     down to the tagline baseline block. The form card is offset by exactly this
     so its top edge meets "Finance, made approachable." rather than the logo - tokenised
     because the offset is only correct while it tracks the mark. */
  --gate-lockup-w: 420px;
  --gate-card-drop: 20px;

  /* The gate's own container inset, and the account grid's gap. Both are named
     because the form card's width is computed FROM them: a literal 28px in that
     calc had to silently agree with a `gap` declared 60 lines away, and an
     inset that was never declared at all. */
  --gate-pad: 1rem;
  /* The gate's own top gap. It must still clear the 60px fixed header, which
     overlays the container rather than pushing it down - but it does NOT need
     the room the app pages leave for their nav row, because the gate hides
     that. 4.5rem puts the mark 12px under the header. */
  --gate-top: 4.5rem;
  --gate-grid-gap: 14px;
}

/* Streamlit sizes this padding for an app with NO top nav, so with
   position="top" it stacks below the bar instead of being absorbed by it -
   which is the dead band between the tabs and the content. */
[data-testid="stMainBlockContainer"] {
  padding-top: var(--fin-top-gap);
  max-width: var(--fin-measure);
  margin-left: auto;
  margin-right: auto;
}

html, body, [class*="st-"] { font-feature-settings: "kern" 1; }

/* Text fields need a visible edge. Streamlit gives the wrapper a 1px border in
   the same colour as its own background, so the box is defined only by its
   fill - and in dark mode that fill is identical to the card it sits on
   (measured: rgb(29,27,33) on rgb(29,27,33)). The field simply was not there.
   Fixed app-wide rather than on the gate alone, because it is the same
   component and the same disappearance on every page. */
[data-testid="stTextInputRootElement"],
.stTextArea [data-baseweb="base-input"],
[data-testid="stChatInput"] {
  border: 1px solid var(--fin-field-line) !important;
  background: var(--fin-note-ground) !important;
}
/* Focus is stated explicitly rather than left to Streamlit's own rule winning
   on specificity - the border above would otherwise swallow the focus ring. */
[data-testid="stTextInputRootElement"]:focus-within,
.stTextArea [data-baseweb="base-input"]:focus-within,
[data-testid="stChatInput"]:focus-within {
  border-color: var(--fin-accent) !important;
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--fin-accent) 28%, transparent);
}

/* Every figure aligns in its column and stops jittering as values update. */
[data-testid="stMetricValue"], [data-testid="stMetricDelta"],
.stDataFrame, code, pre, .fin-num, table td, table th {
  font-variant-numeric: tabular-nums lining-nums;
  font-feature-settings: "tnum" 1, "lnum" 1;
}

/* "Fintor Serif" IS Source Serif 4. It is aliased because Streamlit bundles a
   family called "Source Serif" and silently DROPS a declared fontFace whose
   name collides with it - the face never reached document.fonts at all. */
h1, h2, h3, h4 { font-family: "Fintor Serif", Georgia, serif;
                 letter-spacing: -0.012em; font-weight: 650; }
h1 { font-size: 1.72rem; }

/* Hairline rules instead of drop shadows - restraint reads as considered. */
[data-testid="stMetric"] {
  border: 1px solid var(--fin-line);
  border-radius: 10px;
  padding: 12px 14px 8px;
  background: var(--fin-paper);
}
[data-testid="stSidebar"] { border-right: 1px solid var(--fin-line); }

.fin-chip {
  display: inline-block; padding: 2px 9px; margin: 0 4px 4px 0;
  border: 1px solid var(--fin-line); border-radius: 999px;
  font-size: var(--fs-xs); color: var(--fin-muted); background: var(--fin-paper);
  font-variant-numeric: tabular-nums;
}
/* "live" is a STATE, so it wears the state green (--dot-live, the same green
   as --fin-up), not the brand. When the brand was green these were the same
   colour and the distinction did not matter; now it does, and the nav dot for
   live data would otherwise disagree with the chip that says the same thing. */
.fin-chip-good { border-color: var(--dot-live); color: var(--dot-live); }
.fin-chip-accent { border-color: var(--fin-accent); color: var(--fin-accent); }
.fin-chip-warn { border-color: var(--fin-warn); color: var(--fin-warn); }

.fin-persona {
  border: 1px solid var(--fin-line); border-left: 3px solid var(--fin-accent);
  border-radius: 8px; padding: 10px 12px; background: var(--fin-paper); margin-bottom: 10px;
}
.fin-persona b { font-size: 0.96rem; }
.fin-persona span { color: var(--fin-muted); font-size: var(--fs-sm); }

/* ---- sign-in screen ----
   Two panels: brand on the left, the form and the demo accounts on the right.
   .gate-wrap is gone - Streamlit renders its columns outside any HTML we emit,
   which is why that wrapper never constrained anything. */
/* No leading offset on either: both columns open at the same y, so any padding
   here drops the mark below the form card's top border. Measured - the card
   started at 104 and the logo at 120. */
.signin-brand { padding: 0; }

/* The hero lockup: leaf, wordmark and tagline as one supplied image.
   Width is the only thing to set - the artwork carries its own proportions,
   which is the point of replacing three separately-aligned elements with it. */
.gate-lockup { margin: 0 0 22px; }
.gate-lockup img {
  display: block;
  width: var(--gate-lockup-w);
  max-width: 100%;
  height: auto;
}
/* Two files, one shown. An <img> cannot inherit CSS colour, and choosing
   server-side goes stale the instant the viewer toggles - Streamlit repaints
   without rerunning the script. The probe's data-theme drives this, so the
   swap needs no rerun. */
.gate-lockup .lockup-dark { display: none; }
:root[data-theme="dark"] .gate-lockup .lockup-light { display: none; }
:root[data-theme="dark"] .gate-lockup .lockup-dark { display: block; }

.gate-subline {
  color: var(--fin-muted); margin: 0 0 26px;
  font-size: 1.02rem; line-height: 1.55;
}
.signin-pillar {
  display: grid; grid-template-columns: 10.5rem 1fr; gap: 0.75rem;
  padding: 9px 0; border-top: 1px solid var(--fin-line);
  font-size: var(--fs-sm);
}
/* The stack had a top rule per row and nothing closing it, so the last line
   ran straight into the eyebrow below. */
.signin-pillar:last-of-type { border-bottom: 1px solid var(--fin-line); }
.signin-pillar b { color: var(--fin-ink); font-weight: 600; }
.signin-pillar span { color: var(--fin-muted); }

.gate-ask {
  font-size: var(--fs-xs); letter-spacing: 0.1em; text-transform: uppercase;
  color: var(--fin-accent); margin: 0 0 12px;
}
/* Same eyebrow, but this one opens a full-width band below two panels rather
   than labelling the top of a card. */
.gate-ask-band { margin: 30px 0 14px; }

/* The form card. Keyed container rather than a wrapper div, for the reason
   above - st.container(key=...) emits a st-key-* class we can target. */
.st-key-signin-card {
  border: 1px solid var(--fin-line);
  border-radius: 12px;
  background: var(--fin-paper);
  padding: 20px 22px 18px;
  /* One account card wide, derived from the SAME arithmetic the grid uses -
     three columns and two gaps - so the two cannot drift apart when the
     measure changes. Note the container inset: --fin-measure-gate is a
     BORDER-box width and the grid sits in the content box, so the padding has
     to come off or this lands 53px too wide (measured: 502.7 against 449.3). margin-left:auto rather than centring: it sits in the
     last column, so right-aligning lands its edge on the grid's right edge and
     the card reads as the head of that third column. */
  max-width: calc(
    (var(--fin-measure-gate) - 2 * var(--gate-pad) - 2 * var(--gate-grid-gap)) / 3);
  margin-left: auto;
  /* A deliberate drop, not an alignment. It used to be computed so the card
     met the tagline ELEMENT; the lockup is one image now and there is nothing
     to align to, so this is simply how far the form sits below the top of the
     brand panel. */
  margin-top: var(--gate-card-drop);
}
.st-key-signin-card .stButton > button,
.st-key-signin-card [data-testid="stFormSubmitButton"] > button {
  background: var(--fin-accent);
  border: none;
  border-radius: 8px;
  padding: 10px 14px;
  margin-top: 4px;
}
/* Colour and weight on the inner <p>, not the button: Streamlit styles that
   element directly, and a direct declaration on a child beats an inherited one
   - the same trap that left the active nav tab at 2.74:1. */
.st-key-signin-card [data-testid="stFormSubmitButton"] > button p,
.st-key-signin-card .stButton > button p {
  color: var(--fin-paper) !important;
  font-weight: 600 !important;
}
.signin-help {
  font-size: var(--fs-sm); color: var(--fin-muted); margin: 8px 0 0;
  line-height: 1.5;
}
.signin-help code {
  font-size: var(--fs-xs); padding: 1px 5px; border-radius: 4px;
  background: var(--fin-note-ground); color: var(--fin-ink);
}
/* The username badge. It is the thing you actually type to sign in, so it gets
   the one accent on the card; everything else stays ink and muted. */
.signin-account code {
  font-size: var(--fs-xs); font-weight: 600; padding: 2px 7px; border-radius: 999px;
  background: var(--fin-accent); color: var(--fin-paper);
  letter-spacing: 0.01em;
}

/* The demo accounts: three across, two down, below both panels. Stacked six
   deep in the right-hand column they pushed the last two below the fold, so
   the screen that introduces the personas hid a third of them.

   A real grid, not st.columns. See gate.py::_accounts_band for why - the short
   version is that Streamlit's nested flex wrappers sized the row 16px under
   what the cards needed and clipped the figures off the bottom of five of the
   six. `grid-auto-rows: 1fr` equalises each row of cards by construction, so
   there is nothing left to shrink and nothing to overflow. */
.signin-accounts {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  grid-auto-rows: 1fr;
  gap: var(--gate-grid-gap);
}
@media (max-width: 900px) {
  .signin-accounts { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 620px) {
  .signin-accounts { grid-template-columns: minmax(0, 1fr); }
}
/* Equal-height cells. The row is already flex/stretch, but stColumn is
   display:block, so a stretched column still hands its child a content
   height - the same chain the persona tiles needed. Scoped with :has() so the
   workspace main/rail columns keep Streamlit's default behaviour.

   min-height:auto, NOT 0. `min-height:0` is the standard unlock for a flex
   child that needs to scroll, and it is exactly wrong here: it lets the cell
   shrink below its own content, so the last line escaped the bottom border.
   Measured before the fix - the cell ended at 635.1 and its text at 640.1, a
   5px overhang that also ate the 10px of bottom padding.

   The chain has to be unbroken. Streamlit puts stElementContainer > stMarkdown
   > stMarkdownContainer between the keyed container and our markup; any one of
   them left as display:block re-introduces an auto-height link, and the
   `margin-top:auto` that pins the figures to the bottom stops resolving. */
/* Each card. The border and padding live here now, on an element we emit, so
   the box model is ours and the bottom padding is actually honoured. */
.signin-account {
  display: flex; flex-direction: column;
  border: 1px solid var(--fin-line);
  border-radius: 10px;
  background: var(--fin-card-tint);
  padding: 13px 15px 12px;
  transition: border-color 120ms ease, transform 120ms ease;
}
/* These are not clickable - the hover is an affordance for "this is a unit you
   read", which is what stops six tinted blocks reading as one slab. */
.signin-account:hover { border-color: var(--fin-accent); }
@media (prefers-reduced-motion: reduce) {
  .signin-account { transition: none; }
}
.signin-account-head {
  display: flex; align-items: baseline; gap: 7px; flex-wrap: wrap;
}
.signin-account-name { font-weight: 600; color: var(--fin-ink); }
/* Under the name, not floating right: at a third of the width there is no
   room for a right-aligned column and the figures wrapped. */
/* margin-top:auto on this element resolved to 0px - measured on all six cards -
   so the shortest card left 33px of slack UNDER its figures instead of above.
   Making the quote the flexible element pushes the figures down reliably
   without depending on auto-margin resolution inside a grid item. */
.signin-account-nums {
  margin: 0; padding-top: 8px; color: var(--fin-muted);
  font-size: var(--fs-xs); font-variant-numeric: tabular-nums lining-nums;
  border-top: 1px solid var(--fin-line);
}
.signin-account-head-line {
  margin: 4px 0 3px; font-size: var(--fs-sm); color: var(--fin-muted);
}
.signin-account-journey {
  flex: 1 1 auto; margin: 0 0 8px; font-size: var(--fs-sm); color: var(--fin-ink);
  font-family: "Fintor Serif", Georgia, serif; font-style: italic;
  line-height: 1.4;
}
/* Marks a question two personas share. Without it the repeat reads as a
   mistake instead of as the comparison it is. */
.signin-echo {
  display: block; font-family: "Inter Tight", system-ui, sans-serif;
  font-style: normal; font-size: var(--fs-xs); color: var(--fin-accent);
  margin-top: 2px;
}
/* No max-width. 100ch still wrapped short of the account grid above it, which
   is the edge the eye actually measures against - the rule should run from the
   left border of the first card to the right border of the last. The container
   already is that width, so the cap could only ever make it narrower. */
.gate-foot {
  color: var(--fin-muted); font-size: var(--fs-sm); margin: 0;
  border-top: 1px solid var(--fin-line); padding-top: 12px;
}

/* TOP MARGINS ON GATE PARAGRAPHS NEED THE EXTRA SPECIFICITY.
   Streamlit sets a margin on `[data-testid="stMarkdownContainer"] p`, which is
   (0,1,1) and beats a bare `.gate-foot` at (0,1,0) - so `margin-top` on any of
   these silently computed to 0 while `margin-bottom` came through fine. Two
   earlier spacing fixes did nothing at all because of this: the 30px above
   "Demo accounts", and the 18px that was supposed to keep this rule off the
   bottom of the cards. The rule ended up drawn exactly on the card edge -
   measured gap 0.0px.
   This is the same trap as the nav tab that stayed at 2.74:1: the declaration
   was right and never reached the element. */
[data-testid="stMarkdownContainer"] p.gate-ask-band { margin-top: 30px; }
[data-testid="stMarkdownContainer"] p.gate-foot { margin-top: 24px; }

/* Reference pages are read, not scanned, so they take a narrower measure.
   Headings and figures stay full width; only running text is constrained. */
.fin-prose p, .fin-prose li { max-width: var(--fin-prose); }

/* The header logo. Streamlit pins it to 24px, which renders the lockup too
   small to read in a 60px bar; 34px leaves 13px of clearance top and bottom. */
[data-testid="stHeaderLogo"] {
  height: 34px !important;
  max-height: 34px !important;
  width: auto !important;
}
[data-testid="stLogoLink"] { display: flex; align-items: center; }

/* ---- top navigation ----------------------------------------------------
   Targeted via aria-current and href, never Streamlit's generated emotion class
   hashes, which change between builds. The icons are Material font ligatures, so
   font-size is what sizes them. */

[data-testid="stTopNavLink"] {
  font-size: var(--fs-md) !important;
  font-weight: 500;
  min-height: 38px;
  padding: 6px 14px !important;
  border-radius: 8px;
  gap: 8px;
  background: var(--tab-workspace);
  position: relative;
}
[data-testid="stTopNavLink"] [data-testid="stIconMaterial"] {
  font-size: 20px !important;
  width: 20px; height: 20px;
}
[data-testid="stTopNavLink"]:hover { background: var(--tab-hover); }

/* The page you are on: solid, not a wash. */
[data-testid="stTopNavLink"][aria-current="page"] {
  background: var(--fin-accent) !important;
  color: var(--fin-paper) !important;
  font-weight: 600;
}
/* The label needs its OWN rule, not the inherited colour above.
   Streamlit puts the text in a <p> inside stMarkdownContainer and colours that
   element directly - and a direct declaration on a child beats an inherited
   one from the parent, !important or not. Measured on the active tab before
   this rule existed: rgb(23,33,29) on rgb(31,111,92), 2.74:1. The icon hit the
   same wall and got the rule below; the text never did. */
[data-testid="stTopNavLink"][aria-current="page"] [data-testid="stMarkdownContainer"],
[data-testid="stTopNavLink"][aria-current="page"] [data-testid="stMarkdownContainer"] p {
  color: var(--fin-paper) !important;
}
[data-testid="stTopNavLink"][aria-current="page"] [data-testid="stIconMaterial"] {
  color: var(--fin-paper) !important;
}
/* No "you are here" state for the About pages: measured in the browser, the
   collapsed stTopNavSection dropdown exposes no aria-current on itself or any
   descendant while one of its pages is open, so there is nothing to key off.
   Left unstyled rather than faked - a dead :has() rule reads as working. */

/* Reference material reads as a different family from your workspace. */
[data-testid="stTopNavSection"] {
  background: var(--tab-reference);
  border-radius: 8px;
  font-size: var(--fs-md) !important;
  font-weight: 500;
  min-height: 38px;
  padding: 6px 12px !important;
}
[data-testid="stTopNavSection"] [data-testid="stIconMaterial"] { font-size: 20px !important; }

/* State dots. Colour comes from chrome.nav_state_style(), computed server-side
   from DataStatus and the cost meter - transparent until a real observation,
   so the nav can never claim "live" on a cold load. */
[data-testid="stTopNavLink"][href$="/market"]::after,
[data-testid="stTopNavLink"][href$="/portfolio"]::after,
[data-testid="stTopNavLink"][href$="/internals"]::after {
  content: "";
  width: 7px; height: 7px; border-radius: 50%;
  display: inline-block; margin-left: 2px;
}
[data-testid="stTopNavLink"][href$="/market"]::after { background: var(--dot-market); }
[data-testid="stTopNavLink"][href$="/portfolio"]::after { background: var(--dot-portfolio); }
[data-testid="stTopNavLink"][href$="/internals"]::after { background: var(--dot-internals); }

/* ---- top chrome ---- */
.bc { margin: 0; }
.bc ol { list-style: none; display: flex; flex-wrap: wrap; gap: 6px;
         margin: 0; padding: 0; font-size: var(--fs-sm); color: var(--fin-muted); }
.bc li { display: flex; gap: 6px; align-items: baseline; }
.bc-sep { color: var(--fin-line); }
.bc-now { color: var(--fin-ink); font-weight: 600; }

.ident { display: flex; align-items: baseline; justify-content: flex-end;
         gap: 8px; flex-wrap: wrap; }
.ident-who { font-size: var(--fs-sm); font-weight: 600; }
.ident-sub { color: var(--fin-muted); font-weight: 400; }

.chip, .chip-accent, .chip-warn {
  display: inline-block; padding: 1px 8px; border-radius: 999px;
  border: 1px solid var(--fin-line); background: var(--fin-paper);
  font-size: var(--fs-xs); color: var(--fin-muted);
  font-variant-numeric: tabular-nums;
}
.chip-accent { border-color: var(--fin-accent); color: var(--fin-accent); }
.chip-warn { border-color: var(--fin-warn); color: var(--fin-warn); }

.chrome-rule { border-top: 1px solid var(--fin-line); margin: 8px 0 14px; }

/* Streamlit's own secondary text sits right next to ours, so it takes the same
   floor: the persona summary line on the data pages, and every metric label. */
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p,
[data-testid="stMetricLabel"], [data-testid="stMetricLabel"] p {
  font-size: var(--fs-sm) !important;
}

.prompt-hint {
  font-size: var(--fs-xs); letter-spacing: 0.08em; text-transform: uppercase;
  color: var(--fin-muted); margin: 14px 0 6px;
}

.fin-disclaimer {
  color: var(--fin-muted); font-size: var(--fs-sm); border-top: 1px solid var(--fin-line);
  padding-top: 8px; margin-top: 14px;
}
.fin-cite { font-size: var(--fs-sm); color: var(--fin-muted); }


/* --- cards and the rail ------------------------------------------------
   The selector is an attribute-substring match on the st-key-* class that
   st.container(key=...) emits, because the exact element Streamlit hangs it
   on is an implementation detail and a data-testid would pin the version. */
[class*="st-key-card-"] {
  background: var(--fin-paper);
  border: 1px solid var(--fin-line);
  border-radius: 12px;
  padding: 1.25rem 1.375rem 1.125rem;
}
/* Streamlit's own border on the container would double up with ours. */
[class*="st-key-card-"] > div { border: none; }

/* The probe is machinery, not content: out of the flex flow so it costs no
   gap, but still laid out so the iframe actually loads and runs. */
.st-key-theme-probe {
  position: absolute; width: 0; height: 0; overflow: hidden; pointer-events: none;
}

.fin-card-tag { margin-bottom: 0.5rem; }
.fin-card-head {
  display: flex; align-items: flex-start; justify-content: space-between;
  gap: 1.5rem; margin-bottom: 0.875rem;
}
.fin-card-title {
  font-family: "Fintor Serif", Georgia, serif;
  font-size: 1.125rem; font-weight: 600; color: var(--fin-ink);
  line-height: 1.25;
}
.fin-card-sub {
  font-size: var(--fs-sm); color: var(--fin-muted); margin-top: 0.25rem;
  max-width: 62ch;
}
.fin-card-meta { text-align: right; white-space: nowrap; }
.fin-card-meta span {
  display: block; font-size: var(--fs-xs); color: var(--fin-muted);
}
.fin-card-meta b {
  font-size: 1.625rem; font-weight: 600; color: var(--fin-ink);
  font-variant-numeric: tabular-nums lining-nums;
}

/* "What this shows": the notes under a figure, including what it ignores. */
.fin-note {
  margin-top: 0.875rem; padding: 0.875rem 1rem;
  border-radius: 8px; background: var(--fin-note-ground);
}
.fin-note-title {
  font-size: var(--fs-xs); font-weight: 600; color: var(--fin-ink);
  text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 0.4rem;
}
.fin-note ul { margin: 0; padding-left: 1.1rem; }
.fin-note li {
  font-size: var(--fs-sm); color: var(--fin-muted); line-height: 1.55;
  margin-bottom: 0.2rem;
}
/* The limitation is set apart on purpose - it is the line most likely to be
   skimmed and the one most worth reading. */
.fin-note-limit {
  margin-top: 0.45rem; padding-top: 0.45rem;
  border-top: 1px solid var(--fin-line); list-style: none; margin-left: -1.1rem;
  font-style: italic;
}

.fin-rail-label {
  font-size: var(--fs-xs); color: var(--fin-muted);
  text-transform: uppercase; letter-spacing: 0.04em;
}
.fin-rail-value {
  font-size: 2rem; font-weight: 600; color: var(--fin-ink); line-height: 1.1;
  font-variant-numeric: tabular-nums lining-nums; margin-top: 0.15rem;
}
.fin-rail-note {
  font-size: var(--fs-sm); color: var(--fin-muted); margin-top: 0.4rem;
  line-height: 1.5;
}
.fin-rail-rows { display: flex; flex-direction: column; gap: 0.5rem; }
.fin-rail-row {
  display: grid; grid-template-columns: 1fr auto auto; align-items: baseline;
  gap: 0.5rem; padding-bottom: 0.5rem; border-bottom: 1px solid var(--fin-line);
}
.fin-rail-row:last-child { border-bottom: none; padding-bottom: 0; }
.fin-rail-row span { font-size: var(--fs-sm); color: var(--fin-muted); }
.fin-rail-row b {
  font-size: var(--fs-md); color: var(--fin-ink);
  font-variant-numeric: tabular-nums lining-nums;
}
.fin-delta {
  font-size: var(--fs-xs); font-style: normal; min-width: 4.25rem;
  text-align: right; font-variant-numeric: tabular-nums lining-nums;
  color: var(--fin-muted);
}
.fin-delta.fin-up { color: var(--fin-up); }
.fin-delta.fin-down { color: var(--fin-down); }

/* THEME_RULES is appended here at import time: the light and dark token blocks
   under :root[data-theme="..."], which theme_probe() keeps in sync. Every
   component already styles through the tokens, so swapping them is the whole of
   dark mode. */
</style>
"""


# The dark palette, as a single block. Every colour token in :root is restated
# here; tests/test_theme.py fails if one is missed, because a token that is only
# defined once survives into dark mode unchanged - which is how near-black text
# and a near-white card ground shipped on a dark ground once already.
DARK_TOKENS = """
  --fin-ink: #e7e6eb;
  --fin-muted: #9d99a6;      /* 7.1:1 on #121714 */
  --fin-line: #35323c;
  --fin-accent: #9b7aeb;
  --fin-warn: #d2a248;
  --fin-paper: #1d1b21;
  --fin-note-ground: #221f28;
  --fin-card-tint: #201d28;   /* ink 13.34:1, muted 5.95:1, accent 5.03:1 */
  --fin-field-line: #756e8e;  /* 3.38:1 on the field fill, 3.56:1 on the card */
  --fin-up: #4fbf85;        /* 7.11:1 on the dark card */
  --fin-down: #e8786f;      /* 5.73:1 on the dark card */
  --tab-workspace: rgba(155, 122, 235, 0.16);
  --tab-reference: rgba(154, 165, 160, 0.12);
  --tab-hover: rgba(155, 122, 235, 0.28);
  --dot-live: #4fbf85;
  --dot-cached: #7d8884;
  --dot-attention: #d2a248;
"""

LIGHT_TOKENS = """
  --fin-ink: #1a1820;
  --fin-muted: #585461;
  --fin-line: #d9d6e0;
  --fin-accent: #521fcd;
  --fin-warn: #9a6a1b;
  --fin-paper: #fdfdfd;
  --fin-note-ground: #eeedf1;
  --fin-card-tint: #f3effc;
  --fin-field-line: #837e92;
  --fin-up: #1b7f4e;
  --fin-down: #b4332f;
  --tab-workspace: rgba(82, 31, 205, 0.08);
  --tab-reference: rgba(90, 104, 120, 0.10);
  --tab-hover: rgba(82, 31, 205, 0.16);
  --dot-live: #1b7f4e;
  --dot-cached: #8a948f;
  --dot-attention: #c07c12;
"""

# Both are explicit and both are attribute-scoped, so whichever one the probe
# selects outranks the plain `:root` block below on specificity - including the
# dark block the server emitted for the first paint.
THEME_RULES = (f':root[data-theme="dark"] {{{DARK_TOKENS}}}\n'
               f':root[data-theme="light"] {{{LIGHT_TOKENS}}}\n')
CSS = CSS.replace("</style>", THEME_RULES + "</style>")

DARK_CSS = f"<style>:root {{{DARK_TOKENS}}}</style>"

# Streamlit's theme menu repaints the page WITHOUT rerunning the script, so
# anything the server decided is stale until the next interaction. Measured:
# switching Dark -> Light left black cards with dark text on a light page, and
# pressing Escape did not fix it. Streamlit also stamps no theme attribute and
# exposes no CSS variables - but the colour it paints on [data-testid="stApp"]
# is always current, so the browser reads that and stamps the attribute itself.
#
# st.components.v1.html rather than st.markdown: markdown strips <script>. The
# iframe is same-origin, so window.parent.document is reachable, and height=0
# keeps it out of the layout.
THEME_PROBE = """
<script>
(function () {
  var doc = window.parent.document;
  var app = doc.querySelector('[data-testid="stApp"]');
  if (!app) { return; }
  function stamp() {
    var m = getComputedStyle(app).backgroundColor.match(/\\d+/g);
    if (!m) { return; }
    var l = 0.2126 * m[0] + 0.7152 * m[1] + 0.0722 * m[2];
    var want = l < 128 ? 'dark' : 'light';
    if (doc.documentElement.getAttribute('data-theme') !== want) {
      doc.documentElement.setAttribute('data-theme', want);
    }
  }
  stamp();
  new MutationObserver(stamp).observe(app, {attributes: true});
  // The observer catches the class swap; the interval is the belt-and-braces
  // for a repaint that happens without touching stApp's own attributes.
  setInterval(stamp, 500);
})();
</script>
"""


def theme_probe() -> None:
    """Keep :root[data-theme] in step with whatever Streamlit has painted.

    Wrapped in a keyed container so the CSS has a `st-key-theme-probe` hook.
    Without it the zero-height iframe still consumes one 16px flex `gap` from
    Streamlit's vertical block, which pushed every page down by 16px and undid
    the measured --fin-top-gap.

    Taken out of flow with `position: absolute`, NOT `display: none`: a browser
    is free to skip loading an iframe inside a display:none subtree, and an
    unloaded probe means no theme at all.
    """
    import streamlit.components.v1 as components

    with st.container(key="theme-probe"):
        components.html(THEME_PROBE, height=0)


def inject() -> None:
    """Base tokens, then the dark swap when the viewer is in dark mode.

    The theme is decided in PYTHON, not in CSS, and that is not a stylistic
    preference - it is the only signal that is correct. Measured in the browser:

      * `@media (prefers-color-scheme: dark)` follows the OPERATING SYSTEM. A
        viewer on a light OS who picks "Dark" in Streamlit's own menu gets a dark
        page with the light tokens still in force - a near-white card ground
        under Streamlit's light-on-dark text, which is invisible. It is wrong in
        the other direction too: a dark OS plus "Light" darkens the tokens under
        a light page.
      * `:root[data-theme="dark"]` never matches. Streamlit stamps nothing on
        `<html>` or `<body>` and exposes no CSS custom properties - that selector
        is an Artifacts convention that was carried here on the assumption it
        applied, and it never did.

    `st.context.theme.type` is the one thing that actually knows, so the server
    emits the block rather than asking the browser to work it out.
    """
    st.markdown(CSS, unsafe_allow_html=True)
    if is_dark():
        # First-paint accuracy only. The probe's attribute-scoped rules outrank
        # this the moment they land, so a stale value here cannot persist.
        st.markdown(DARK_CSS, unsafe_allow_html=True)
    theme_probe()


def chip(label: str, kind: str = "") -> str:
    cls = {"good": "fin-chip fin-chip-good",
           "accent": "fin-chip fin-chip-accent",
           "warn": "fin-chip fin-chip-warn"}.get(kind, "fin-chip")
    return f'<span class="{cls}">{label}</span>'


def is_dark() -> bool:
    """Whether the viewer is currently in dark mode.

    `config.toml` deliberately omits `base`, so the palette follows the viewer's
    preference rather than being pinned. CSS handles that through media queries,
    but Plotly figures are built in Python and have to be *told* - without this
    the charts keep their light hues on a dark page.

    Defaults to light on anything unexpected: `st.context` is unavailable outside
    a script run (tests, the fonts generator), and a wrong guess here is a
    cosmetic miss, never an error worth raising.
    """
    try:
        return st.context.theme.type == "dark"
    except Exception:  # noqa: BLE001 - no script context, or an older Streamlit
        return False
