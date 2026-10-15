/**
 * SoundToggle.tsx — turns the optional tick/chime sounds on or off (off by default).
 * The first click also unlocks the browser's audio system (autoplay rules require a user gesture).
 */
import { SpeakerHigh, SpeakerSlash } from '@phosphor-icons/react';
import { chime, unlockAudio } from '../../lib/sound';
import { usePrefs } from '../../lib/theme';
import s from './layout.module.css';

export function SoundToggle() {
  const { sound, setSound } = usePrefs();
  return (
    <button
      type="button"
      className={s.iconBtn}
      aria-pressed={sound}
      aria-label={sound ? 'Turn sounds off' : 'Turn sounds on'}
      title={sound ? 'Sounds on' : 'Sounds off'}
      onClick={() => {
        unlockAudio();
        const next = !sound;
        setSound(next);
        if (next) setTimeout(chime, 30);
      }}
    >
      {sound ? <SpeakerHigh size={22} weight="light" /> : <SpeakerSlash size={22} weight="light" />}
    </button>
  );
}
