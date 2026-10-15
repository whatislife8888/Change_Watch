/**
 * Landing.tsx — the logged-out home page.
 *
 * - Hero: a large dial that engraves itself on load and shows the current time. As you type a URL, the
 *   pattern cross-fades to that page's own dial (via the public /api/url/preview endpoint).
 * - "Start watching" carries the URL through sign-up straight into Add page.
 * - The one scroll-linked scene: the dial tilts back (CSS 3D) and separates into four layers, each a
 *   real step of the pipeline: Render, Filter, Compare, Alert (Motion useScroll + useTransform).
 * - The four hard questions, answered.
 * - Lenis smooth scrolling is enabled on this page only (and not at all with reduced motion).
 */
import Lenis from 'lenis';
import { motion, useScroll, useTransform, type MotionValue } from 'motion/react';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { Dial } from '../components/dial/Dial';
import { guillochePaths } from '../components/dial/guilloche';
import { Footer } from '../components/layout/PageShell';
import { TopBar } from '../components/layout/TopBar';
import { Button } from '../components/ui/Button';
import { usePrefersReducedMotion } from '../design/motion';
import { useUrlPreview } from './AddPage';
import s from './Landing.module.css';

const HERO_SEED = 'c0ffee15';

const STEPS = [
  { title: 'Render', body: 'A real browser opens the page, waits for it to settle and takes a full screenshot. JavaScript-built pages work too.' },
  { title: 'Filter', body: 'Timestamps, ads, counters, rotating banners and random tokens are removed. Parts that change on every load are learned and ignored.' },
  { title: 'Compare', body: 'Text and screenshot differences, word by word and pixel by pixel. Any two versions, side by side, under a loupe.' },
  { title: 'Alert', body: 'Email, Telegram or Discord, once per real change, with a one-line summary and a link to the comparison.' },
];

const QUESTIONS = [
  { q: 'Is a site outage or a CAPTCHA a change?', a: 'No. Every check is classified first. Timeouts, server errors and bot walls are marked as errors or blocks, never saved as a new version. Your last good version stays the baseline, so recovery never looks like everything changed.' },
  { q: 'If 200 people watch the same page, is it fetched 200 times?', a: 'Once. Addresses are normalised so tracking parameters don’t create duplicates, and every watcher’s regions and noise rules are evaluated from the same render. If the server says nothing changed, we skip the browser entirely.' },
  { q: 'What about pages that are different on every load?', a: 'When something looks changed we load the page again ten seconds later. Whatever differs between those two loads is noise, so we learn it and ignore it from then on. Sensitivity levels and a flapping guard catch the rest.' },
  { q: 'Doesn’t this hammer websites?', a: 'One request at a time per site, at least ten seconds apart. We respect robots.txt and Crawl-delay, honour Retry-After, back off after errors, check at most every 15 minutes, and identify ourselves honestly.' },
];

/** One layer of the exploded dial. `spread` (0..1) lifts it off the stack along the Z axis; the layer
 * brightens when its step is reached in the scroll. */
function Layer({ index, spread, progress, reduced, children }: {
  index: number; spread: MotionValue<number>; progress: MotionValue<number>; reduced: boolean; children: React.ReactNode;
}) {
  const start = 0.3 + index * 0.12;
  const z = useTransform(spread, (v) => v * index * 64);
  const opacity = useTransform(progress, [start - 0.08, start], reduced ? [1, 1] : [0.55, 1]);
  return (
    <motion.div className={s.layer} style={{ z, opacity }}>
      {children}
    </motion.div>
  );
}

function StepLabel({ i, progress, step }: { i: number; progress: MotionValue<number>; step: (typeof STEPS)[number] }) {
  const start = 0.3 + i * 0.12;
  const opacity = useTransform(progress, [start - 0.08, start], [0.28, 1]);
  return (
    <motion.li className={s.step} style={{ opacity }}>
      <span className={s.stepNum}>{i + 1}</span>
      <div>
        <h3 className={s.stepTitle}>{step.title}</h3>
        <p className={s.stepBody}>{step.body}</p>
      </div>
    </motion.li>
  );
}

/** The exploded-view scroll scene. */
function Pipeline() {
  const ref = useRef<HTMLElement>(null);
  const reduced = usePrefersReducedMotion();
  const { scrollYProgress } = useScroll({ target: ref, offset: ['start start', 'end end'] });
  const tilt = useTransform(scrollYProgress, [0, 0.3], reduced ? [55, 55] : [0, 55]);
  const spread = useTransform(scrollYProgress, [0.12, 0.7], reduced ? [1, 1] : [0, 1]);
  // As the layers rise, move the whole stack down so the top layer never reaches the heading.
  const drop = useTransform(spread, (v) => v * 70);
  const lines = guillochePaths(HERO_SEED, { radius: 100, detail: 'md' });

  return (
    <section ref={ref} className={s.pipeline} aria-label="How ChangeWatch works">
      <div className={s.sticky}>
        <div className="container">
          <h2 className={s.sectionTitle}>Four layers, one movement</h2>
        </div>
        <div className={`container ${s.pipelineGrid}`}>
          <div className={s.stage} aria-hidden="true">
            <motion.div className={s.stack} style={{ rotateX: tilt, y: drop }}>
              <Layer index={0} spread={spread} progress={scrollYProgress} reduced={reduced}>
                {/* Render: the page itself, as a screenshot plate */}
                <svg viewBox="-100 -100 200 200" className={s.layerSvg}>
                  <circle r="96" className={s.plate} />
                  {Array.from({ length: 9 }, (_, i) => (
                    <rect key={i} x={-62} y={-60 + i * 14} width={i % 3 === 0 ? 90 : 124} height={6} rx={3} className={s.textBar} />
                  ))}
                </svg>
              </Layer>
              <Layer index={1} spread={spread} progress={scrollYProgress} reduced={reduced}>
                {/* Filter: the engraving, i.e. what remains once noise is removed */}
                <svg viewBox="-100 -100 200 200" className={s.layerSvg}>
                  <g fill="none" stroke="var(--engrave)" strokeWidth="0.5">
                    {lines.map((p, i) => <path key={i} d={p.d} opacity={p.opacity * 0.9} />)}
                  </g>
                </svg>
              </Layer>
              <Layer index={2} spread={spread} progress={scrollYProgress} reduced={reduced}>
                {/* Compare: the chapter ring that measures */}
                <svg viewBox="-100 -100 200 200" className={s.layerSvg}>
                  <circle r="93" fill="none" stroke="var(--dial-tick)" strokeWidth="0.8" />
                  <circle r="88" fill="none" stroke="var(--dial-tick)" strokeWidth="0.6" />
                  {Array.from({ length: 60 }, (_, i) => {
                    const a = (i / 60) * Math.PI * 2;
                    const r1 = i % 5 === 0 ? 82 : 88;
                    return <line key={i} x1={r1 * Math.sin(a)} y1={-r1 * Math.cos(a)} x2={93 * Math.sin(a)} y2={-93 * Math.cos(a)} stroke="var(--dial-tick)" strokeWidth={i % 5 === 0 ? 1.6 : 0.6} />;
                  })}
                </svg>
              </Layer>
              <Layer index={3} spread={spread} progress={scrollYProgress} reduced={reduced}>
                {/* Alert: the blued hand and the jewel */}
                <svg viewBox="-100 -100 200 200" className={s.layerSvg}>
                  <path d="M -1.6 16 L -0.5 -84 L 0.5 -84 L 1.6 16 Z" fill="var(--blued)" transform="rotate(38)" />
                  <circle r="6" fill="var(--blued-deep)" stroke="var(--blued)" />
                  <circle cy="-62" r="7" fill="var(--lume)" />
                  <circle cx="-2.4" cy="-64.6" r="1.6" fill="#fff" />
                </svg>
              </Layer>
            </motion.div>
          </div>
          <ol className={s.steps}>
            {STEPS.map((step, i) => <StepLabel key={step.title} i={i} progress={scrollYProgress} step={step} />)}
          </ol>
        </div>
      </div>
    </section>
  );
}

export default function Landing() {
  const navigate = useNavigate();
  const reduced = usePrefersReducedMotion();
  const [url, setUrl] = useState('');
  const { preview } = useUrlPreview(url);
  const seed = preview?.valid && preview.dial_seed ? preview.dial_seed : HERO_SEED;

  // Smooth scrolling for this page only.
  useEffect(() => {
    if (reduced) return;
    const lenis = new Lenis({ lerp: 0.1 });
    let frame = 0;
    const raf = (time: number) => {
      lenis.raf(time);
      frame = requestAnimationFrame(raf);
    };
    frame = requestAnimationFrame(raf);
    return () => {
      cancelAnimationFrame(frame);
      lenis.destroy();
    };
  }, [reduced]);

  function start(e: FormEvent) {
    e.preventDefault();
    navigate(url.trim() ? `/signup?url=${encodeURIComponent(url.trim())}` : '/signup');
  }

  return (
    <div className={s.page}>
      <TopBar />
      <main id="main">
        <section className={`container ${s.hero}`}>
          <div className={s.heroDial}>
            <Dial seed={seed} size={560} clock engrave crossfade interactive decorative />
          </div>
          <h1 className={s.headline}>Nothing changes unnoticed.</h1>
          <p className={s.lede}>
            ChangeWatch watches the pages you care about, ignores the noise, and tells you the moment something real changes.
          </p>
          <form className={s.form} onSubmit={start}>
            <label htmlFor="hero-url" className="visually-hidden">Page address</label>
            <input id="hero-url" className={s.input} value={url} onChange={(e) => setUrl(e.target.value)}
              placeholder="Paste a page you want to watch" inputMode="url" autoComplete="url" spellCheck={false} />
            <Button type="submit" variant="primary">Start watching</Button>
          </form>
          <p className={s.note} aria-live="polite">
            {preview?.valid ? <>That's the dial for <strong>{preview.domain}</strong>. Every page gets its own, engraved from its address.</>
              : preview && !preview.valid && url.trim() ? preview.error : 'Every page gets its own dial, engraved from its address.'}
          </p>
        </section>

        <Pipeline />

        <section className={`container ${s.questions}`}>
          <h2 className={s.sectionTitle}>The hard questions, answered</h2>
          <div className={s.qaGrid}>
            {QUESTIONS.map((item) => (
              <div key={item.q} className={s.qa}>
                <h3 className={s.q}>{item.q}</h3>
                <p className={s.a}>{item.a}</p>
              </div>
            ))}
          </div>
        </section>
      </main>
      <Footer />
    </div>
  );
}
