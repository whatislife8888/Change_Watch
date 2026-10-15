/**
 * Settings.tsx — profile and timezone, alert channels (each with a status and "Send test"), the daily
 * digest, and appearance. Sections are separated by hairlines, not boxed in cards.
 */
import { useEffect, useMemo, useState, type FormEvent, type ReactNode } from 'react';
import { toast } from 'sonner';
import { ApiError } from '../api/client';
import { useSaveSettings, useSettings, useTestAlert } from '../api/hooks';
import type { UserSettings } from '../api/types';
import { PageShell } from '../components/layout/PageShell';
import { Button } from '../components/ui/Button';
import { Input, Switch } from '../components/ui/Input';
import { Skeleton, StatusText } from '../components/ui/misc';
import { SegmentedControl } from '../components/ui/SegmentedControl';
import { Select } from '../components/ui/Select';
import { unlockAudio } from '../lib/sound';
import { usePrefs, type Theme } from '../lib/theme';
import s from './Settings.module.css';

function Section({ title, children, aside }: { title: string; children: ReactNode; aside?: ReactNode }) {
  return (
    <section className={s.section}>
      <div className={s.sectionHead}>
        <h2 className={s.sectionTitle}>{title}</h2>
        {aside}
      </div>
      <div className={s.sectionBody}>{children}</div>
    </section>
  );
}

function ChannelStatus({ ready }: { ready: boolean }) {
  return ready ? <StatusText status="ok">Connected</StatusText> : <StatusText status="paused">Not set up</StatusText>;
}

function TestButton({ channel, disabled }: { channel: 'email' | 'telegram' | 'discord'; disabled: boolean }) {
  const test = useTestAlert();
  return (
    <Button size="sm" variant="secondary" disabled={disabled} loading={test.isPending} onClick={() => test.mutate(channel, {
      onSuccess: (r) => toast(r.message),
      onError: (e) => toast(e instanceof ApiError ? e.message : 'Test failed.'),
    })}>Send test</Button>
  );
}

function Form({ data }: { data: UserSettings }) {
  const save = useSaveSettings();
  const { theme, setTheme, sound, setSound } = usePrefs();
  const [name, setName] = useState(data.display_name);
  const [tz, setTz] = useState(data.timezone);
  const [chat, setChat] = useState(data.telegram_chat_id ?? '');
  const [ownBot, setOwnBot] = useState('');
  const [webhook, setWebhook] = useState(data.discord_webhook_url ?? '');
  const [daily, setDaily] = useState(data.digest_mode === 'daily');
  const [hour, setHour] = useState(data.digest_hour);

  useEffect(() => { setChat(data.telegram_chat_id ?? ''); setWebhook(data.discord_webhook_url ?? ''); }, [data.telegram_chat_id, data.discord_webhook_url]);

  const zones = useMemo(() => {
    let list: string[];
    try {
      list = (Intl as unknown as { supportedValuesOf: (k: string) => string[] }).supportedValuesOf('timeZone');
    } catch {
      list = ['Asia/Kolkata', 'UTC', 'Europe/London', 'America/New_York'];
    }
    // Browsers still use the old name "Asia/Calcutta"; the server (and the spec) use "Asia/Kolkata".
    const fixed = list.map((z) => (z === 'Asia/Calcutta' ? 'Asia/Kolkata' : z));
    return [...new Set([data.timezone, ...fixed])].sort();
  }, [data.timezone]);

  const submit = (body: Parameters<typeof save.mutate>[0], done: string) => (e?: FormEvent) => {
    e?.preventDefault();
    save.mutate(body, {
      onSuccess: () => toast(done),
      onError: (err) => toast(err instanceof ApiError ? err.message : 'Could not save.'),
    });
  };

  const telegramReady = data.telegram_available && !!data.telegram_chat_id;
  const discordReady = !!data.discord_webhook_url;

  return (
    <>
      <Section title="Profile">
        <form className={s.form} onSubmit={submit({ display_name: name, timezone: tz }, 'Profile saved.')}>
          <div className={s.two}>
            <Input label="Name" value={name} onChange={(e) => setName(e.target.value)} maxLength={80} />
            <Input label="Email" value={data.email} readOnly hint="Change alerts are sent here." />
          </div>
          <Select label="Timezone" value={tz} onChange={(e) => setTz(e.target.value)} hint="Times in alerts and the daily digest use this timezone.">
            {zones.map((z) => <option key={z} value={z}>{z.replace(/_/g, ' ')}</option>)}
          </Select>
          <div><Button type="submit" variant="primary" loading={save.isPending}>Save profile</Button></div>
        </form>
      </Section>

      <Section title="Alerts">
        <p className="muted">Choose channels per page in each page's settings. Every change is sent at most once per channel.</p>

        <div className={s.channel}>
          <div className={s.channelHead}>
            <h3>Email</h3>
            <ChannelStatus ready={data.email_available} />
          </div>
          <p className="muted small">
            {data.email_available ? `Alerts go to ${data.email}.` : 'The server has no email credentials yet (SMTP or Resend). Alerts are recorded but not emailed.'}
          </p>
          <div><TestButton channel="email" disabled={!data.email_available} /></div>
        </div>

        <form className={s.channel} onSubmit={submit({ telegram_chat_id: chat, ...(ownBot ? { telegram_bot_token: ownBot } : {}) }, 'Telegram settings saved.')}>
          <div className={s.channelHead}>
            <h3>Telegram</h3>
            <ChannelStatus ready={telegramReady} />
          </div>
          <ol className={s.steps}>
            <li>{data.telegram_bot_username ? <>Open Telegram and start a chat with <a href={`https://t.me/${data.telegram_bot_username}`} target="_blank" rel="noreferrer">@{data.telegram_bot_username}</a> (press Start).</> : 'Create a bot with @BotFather and paste its token below, or ask the admin to set one up.'}</li>
            <li>Message <a href="https://t.me/userinfobot" target="_blank" rel="noreferrer">@userinfobot</a>. It replies with your numeric id.</li>
            <li>Paste that number here and save, then press Send test.</li>
          </ol>
          <div className={s.two}>
            <Input label="Chat id" value={chat} onChange={(e) => setChat(e.target.value)} placeholder="123456789" inputMode="numeric" />
            {!data.telegram_available || data.telegram_has_own_bot ? (
              <Input label="Bot token (optional)" value={ownBot} onChange={(e) => setOwnBot(e.target.value)}
                placeholder={data.telegram_has_own_bot ? 'Saved. Paste a new one to replace it.' : '123456:ABC...'} type="password" autoComplete="off" />
            ) : null}
          </div>
          <div className={s.row}>
            <Button type="submit" size="sm" variant="primary" loading={save.isPending}>Save</Button>
            <TestButton channel="telegram" disabled={!telegramReady} />
          </div>
        </form>

        <form className={s.channel} onSubmit={submit({ discord_webhook_url: webhook }, 'Discord settings saved.')}>
          <div className={s.channelHead}>
            <h3>Discord</h3>
            <ChannelStatus ready={discordReady} />
          </div>
          <p className="muted small">In your Discord server: Server settings, then Integrations, then Webhooks, then New webhook. Copy its URL here.</p>
          <Input label="Webhook URL" value={webhook} onChange={(e) => setWebhook(e.target.value)} placeholder="https://discord.com/api/webhooks/..." spellCheck={false} />
          <div className={s.row}>
            <Button type="submit" size="sm" variant="primary" loading={save.isPending}>Save</Button>
            <TestButton channel="discord" disabled={!discordReady} />
          </div>
        </form>
      </Section>

      <Section title="Daily digest">
        <Switch label="Send one daily summary instead of instant alerts"
          hint="Changes are collected and sent together once a day. If nothing changed, nothing is sent."
          checked={daily} onChange={(e) => { setDaily(e.target.checked); submit({ digest_mode: e.target.checked ? 'daily' : 'instant' }, e.target.checked ? 'Daily digest on.' : 'Instant alerts on.')(); }} />
        {daily && (
          <div className={s.narrow}>
            <Select label="Send at" value={hour} onChange={(e) => { const h = Number(e.target.value); setHour(h); submit({ digest_hour: h }, 'Digest time saved.')(); }}>
              {Array.from({ length: 24 }, (_, h) => (
                <option key={h} value={h}>{new Date(2026, 0, 1, h).toLocaleTimeString('en-IN', { hour: 'numeric', hour12: true })}</option>
              ))}
            </Select>
          </div>
        )}
      </Section>

      <Section title="Appearance">
        <div className={s.row}>
          <SegmentedControl<Theme> label="Theme" value={theme} onChange={setTheme}
            options={[{ value: 'fume', label: 'Fumé (dark)' }, { value: 'opaline', label: 'Opaline (light)' }]} />
        </div>
        <Switch label="Sounds" hint="A soft tick when a check finishes and a two-note chime when a page changes."
          checked={sound} onChange={(e) => { unlockAudio(); setSound(e.target.checked); }} />
      </Section>
    </>
  );
}

export default function Settings() {
  const { data, isLoading } = useSettings();
  return (
    <PageShell>
      <h1 className={s.title}>Settings</h1>
      {isLoading || !data ? <div className={s.loading}><Skeleton height={48} /><Skeleton height={48} /><Skeleton height={48} /></div> : <Form data={data} />}
    </PageShell>
  );
}
