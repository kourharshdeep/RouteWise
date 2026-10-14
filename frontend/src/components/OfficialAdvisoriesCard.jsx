import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ShieldCheck, PhoneCall, ExternalLink, AlertCircle, RefreshCw, Radio } from 'lucide-react';
import { fetchOfficialAdvisories } from '../services/api';

export default function OfficialAdvisoriesCard() {
  const { t } = useTranslation();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const res = await fetchOfficialAdvisories();
        setData(res);
      } catch (err) {
        console.warn('Failed to load official advisories:', err);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  if (loading) return null;
  if (!data) return null;

  return (
    <div className="official-advisories-card" role="region" aria-label="Official Traffic Advisories">
      <div className="adv-card-header">
        <div className="adv-card-badge-row">
          <span className="badge badge-official">
            <ShieldCheck size={13} style={{ display: 'inline', marginRight: 4 }} />
            Official Authority
          </span>
          <span className="adv-verified-date">
            Verified: {data.last_verified}
          </span>
        </div>
        <h3 className="adv-card-title">{data.authority}</h3>
        <p className="adv-card-disclaimer">
          {data.disclaimer}
        </p>
      </div>

      <div className="adv-card-grid">
        {/* Official Channels */}
        <div className="adv-channels-col">
          <h4 className="adv-section-title">
            <Radio size={15} /> Official Status Broadcasts
          </h4>
          <div className="adv-channels-list">
            {data.official_channels?.map((ch) => (
              <a
                key={ch.platform}
                href={ch.url}
                target="_blank"
                rel="noopener noreferrer"
                className="adv-channel-link"
              >
                <div className="adv-ch-left">
                  <strong className="adv-ch-platform">{ch.platform}</strong>
                  <span className="adv-ch-handle">{ch.handle}</span>
                  <span className="adv-ch-desc">{ch.description}</span>
                </div>
                <ExternalLink size={14} className="adv-ext-icon" />
              </a>
            ))}
          </div>
        </div>

        {/* TCU Control Room Contacts */}
        <div className="adv-tcu-col">
          <h4 className="adv-section-title">
            <PhoneCall size={15} /> Traffic Control Units (TCU)
          </h4>
          <div className="adv-tcu-list">
            {data.control_units?.map((u) => (
              <div key={u.unit} className="tcu-unit-card">
                <strong className="tcu-name">{u.unit}</strong>
                <div className="tcu-numbers">
                  <a href={`tel:${u.phone}`} className="tcu-phone-btn">
                    <PhoneCall size={12} /> {u.phone}
                  </a>
                  {u.landline && (
                    <span className="tcu-landline">({u.landline})</span>
                  )}
                </div>
                <span className="tcu-role">{u.role}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
