// Known translations are split into real lazy chunks; unknown languages use English.
const loaders = import.meta.glob("../../public/i18n/*/translation.json");
export async function loadLanguage(lang) {
  const loader =
    loaders[`../../public/i18n/${lang}/translation.json`] ||
    loaders["../../public/i18n/en/translation.json"];
  return loader();
}
