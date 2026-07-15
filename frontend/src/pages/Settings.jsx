import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api.js';
import { clearToken } from '../auth.js';
import { useLang } from '../i18n.jsx';

export default function Settings() {
  const { t } = useLang();
  const navigate = useNavigate();

  const [currentPw, setCurrentPw] = useState('');
  const [newPw, setNewPw] = useState('');
  const [pwError, setPwError] = useState(null);
  const [pwOk, setPwOk] = useState(false);

  const [deletePw, setDeletePw] = useState('');
  const [deleteError, setDeleteError] = useState(null);

  const [telegram, setTelegram] = useState(null);
  const [telegramTimezone, setTelegramTimezone] = useState('UTC');
  const [telegramEnabled, setTelegramEnabled] = useState(false);
  const [telegramError, setTelegramError] = useState(null);
  const [telegramOk, setTelegramOk] = useState(false);
  const [telegramTestOk, setTelegramTestOk] = useState(false);

  useEffect(() => {
    let active = true;
    api.getTelegramSettings()
      .then((data) => {
        if (!active) return;
        setTelegram(data);
        setTelegramTimezone(data.timezone);
        setTelegramEnabled(data.notifications_enabled);
      })
      .catch((err) => {
        if (active) setTelegramError(err.message);
      });
    return () => {
      active = false;
    };
  }, []);

  const changePassword = async (e) => {
    e.preventDefault();
    setPwError(null);
    setPwOk(false);
    try {
      await api.changePassword(currentPw, newPw);
      setPwOk(true);
      setCurrentPw('');
      setNewPw('');
    } catch (err) {
      setPwError(err.message);
    }
  };

  const deleteAccount = async (e) => {
    e.preventDefault();
    setDeleteError(null);
    if (!window.confirm(t('settings.confirmDelete'))) return;
    try {
      await api.deleteAccount(deletePw);
      clearToken();
      navigate('/login', { replace: true });
    } catch (err) {
      setDeleteError(err.message);
    }
  };

  const saveTelegram = async (e) => {
    e.preventDefault();
    setTelegramError(null);
    setTelegramOk(false);
    setTelegramTestOk(false);
    try {
      const data = await api.updateTelegramSettings(telegramEnabled, telegramTimezone);
      setTelegram(data);
      setTelegramTimezone(data.timezone);
      setTelegramEnabled(data.notifications_enabled);
      setTelegramOk(true);
    } catch (err) {
      setTelegramError(err.message);
    }
  };

  const regenerateTelegramToken = async () => {
    setTelegramError(null);
    setTelegramOk(false);
    setTelegramTestOk(false);
    try {
      const data = await api.regenerateTelegramToken();
      setTelegram(data);
      setTelegramTimezone(data.timezone);
      setTelegramEnabled(data.notifications_enabled);
    } catch (err) {
      setTelegramError(err.message);
    }
  };

  const sendTelegramTest = async () => {
    setTelegramError(null);
    setTelegramOk(false);
    setTelegramTestOk(false);
    try {
      await api.sendTelegramTestMessage();
      setTelegramTestOk(true);
    } catch (err) {
      setTelegramError(err.message);
    }
  };

  return (
    <div className="settings-page">
      <h1>{t('settings.title')}</h1>

      <section className="settings-card">
        <h2>{t('settings.changePasswordTitle')}</h2>
        <form onSubmit={changePassword}>
          <label>
            {t('settings.currentPassword')}
            <input
              type="password"
              value={currentPw}
              onChange={(e) => setCurrentPw(e.target.value)}
              required
              autoComplete="current-password"
            />
          </label>
          <label>
            {t('settings.newPassword')}
            <input
              type="password"
              value={newPw}
              onChange={(e) => setNewPw(e.target.value)}
              required
              minLength={6}
              autoComplete="new-password"
            />
          </label>
          {pwError && <div className="error">{pwError}</div>}
          {pwOk && <div className="success">{t('settings.passwordChanged')}</div>}
          <button type="submit" className="btn btn-primary">{t('settings.submit')}</button>
        </form>
      </section>

      <section className="settings-card">
        <h2>{t('settings.telegramTitle')}</h2>
        {telegram && (
          <>
            <p className="settings-hint">
              {telegram.bot_configured
                ? t('settings.telegramHint')
                : t('settings.telegramBotMissing')}
            </p>
            <div className="telegram-status">
              <span>{t('settings.telegramStatus')}</span>
              <strong>
                {telegram.chat_id ? t('settings.telegramLinked') : t('settings.telegramNotLinked')}
              </strong>
            </div>
            <div className="telegram-token">
              <code>/start {telegram.link_token}</code>
              <button type="button" className="btn btn-ghost" onClick={regenerateTelegramToken}>
                {t('settings.telegramRegenerate')}
              </button>
            </div>
            {telegram.deep_link && (
              <a className="telegram-link btn" href={telegram.deep_link} target="_blank" rel="noreferrer">
                {t('settings.telegramOpenBot')}
              </a>
            )}
            <form onSubmit={saveTelegram}>
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={telegramEnabled}
                  onChange={(e) => setTelegramEnabled(e.target.checked)}
                />
                {t('settings.telegramEnable')}
              </label>
              <label>
                {t('settings.telegramTimezone')}
                <input
                  value={telegramTimezone}
                  onChange={(e) => setTelegramTimezone(e.target.value)}
                  placeholder="UTC"
                  required
                />
              </label>
              {telegramError && <div className="error">{telegramError}</div>}
              {telegramOk && <div className="success">{t('settings.telegramSaved')}</div>}
              {telegramTestOk && <div className="success">{t('settings.telegramTestSent')}</div>}
              <div className="settings-actions">
                <button type="submit" className="btn btn-primary">{t('settings.telegramSave')}</button>
                <button type="button" className="btn" onClick={sendTelegramTest}>
                  {t('settings.telegramSendTest')}
                </button>
              </div>
            </form>
          </>
        )}
        {!telegram && !telegramError && <p className="settings-hint">{t('settings.telegramLoading')}</p>}
        {!telegram && telegramError && <div className="error">{telegramError}</div>}
      </section>

      <section className="settings-card danger">
        <h2>{t('settings.dangerZone')}</h2>
        <h3>{t('settings.deleteAccountTitle')}</h3>
        <p className="settings-hint">{t('settings.deleteAccountHint')}</p>
        <form onSubmit={deleteAccount}>
          <label>
            {t('settings.confirmPassword')}
            <input
              type="password"
              value={deletePw}
              onChange={(e) => setDeletePw(e.target.value)}
              required
              autoComplete="current-password"
            />
          </label>
          {deleteError && <div className="error">{deleteError}</div>}
          <button type="submit" className="btn btn-danger">{t('settings.deleteAccount')}</button>
        </form>
      </section>
    </div>
  );
}
