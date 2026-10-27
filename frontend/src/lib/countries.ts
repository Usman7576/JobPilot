/** Common countries for location preferences (ISO 3166-1 alpha-2, lowercase). */
export const COUNTRIES: { code: string; name: string }[] = [
  { code: "us", name: "United States" },
  { code: "gb", name: "United Kingdom" },
  { code: "ca", name: "Canada" },
  { code: "au", name: "Australia" },
  { code: "de", name: "Germany" },
  { code: "nl", name: "Netherlands" },
  { code: "fr", name: "France" },
  { code: "es", name: "Spain" },
  { code: "it", name: "Italy" },
  { code: "ie", name: "Ireland" },
  { code: "ch", name: "Switzerland" },
  { code: "at", name: "Austria" },
  { code: "be", name: "Belgium" },
  { code: "se", name: "Sweden" },
  { code: "pl", name: "Poland" },
  { code: "pt", name: "Portugal" },
  { code: "ae", name: "United Arab Emirates" },
  { code: "sa", name: "Saudi Arabia" },
  { code: "qa", name: "Qatar" },
  { code: "pk", name: "Pakistan" },
  { code: "in", name: "India" },
  { code: "bd", name: "Bangladesh" },
  { code: "sg", name: "Singapore" },
  { code: "my", name: "Malaysia" },
  { code: "nz", name: "New Zealand" },
  { code: "za", name: "South Africa" },
  { code: "br", name: "Brazil" },
  { code: "mx", name: "Mexico" },
  { code: "jp", name: "Japan" },
];

export function countryName(code: string) {
  return COUNTRIES.find((c) => c.code === code)?.name ?? code.toUpperCase();
}
