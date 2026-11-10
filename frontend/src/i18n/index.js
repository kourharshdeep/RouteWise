import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

import en from './locales/en.json';
import hi from './locales/hi.json';

const savedLang = typeof localStorage !== 'undefined' ? localStorage.getItem('routewise_lang') || 'en' : 'en';

i18n
  .use(initReactI18next)
  .init({
    resources: {
      en: { translation: en },
      hi: { translation: hi },
    },
    lng: savedLang,
    fallbackLng: 'en',
    interpolation: {
      escapeValue: false, // React already escapes values
    },
  });

export function changeLanguage(lang) {
  i18n.changeLanguage(lang);
  if (typeof localStorage !== 'undefined') localStorage.setItem('routewise_lang', lang);
}

export default i18n;
