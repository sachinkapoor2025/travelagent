/** Major airports for autocomplete — city name, IATA code, country */
window.TRAVELAI_AIRPORTS = [
  { code: "DEL", city: "New Delhi", name: "Indira Gandhi Intl", country: "India" },
  { code: "BOM", city: "Mumbai", name: "Chhatrapati Shivaji", country: "India" },
  { code: "BLR", city: "Bangalore", name: "Kempegowda Intl", country: "India" },
  { code: "MAA", city: "Chennai", name: "Chennai Intl", country: "India" },
  { code: "HYD", city: "Hyderabad", name: "Rajiv Gandhi Intl", country: "India" },
  { code: "CCU", city: "Kolkata", name: "Netaji Subhash", country: "India" },
  { code: "AMD", city: "Ahmedabad", name: "Sardar Vallabhbhai Patel", country: "India" },
  { code: "PNQ", city: "Pune", name: "Pune Airport", country: "India" },
  { code: "GOI", city: "Goa", name: "Dabolim", country: "India" },
  { code: "COK", city: "Kochi", name: "Cochin Intl", country: "India" },
  { code: "DXB", city: "Dubai", name: "Dubai Intl", country: "UAE" },
  { code: "AUH", city: "Abu Dhabi", name: "Zayed Intl", country: "UAE" },
  { code: "SHJ", city: "Sharjah", name: "Sharjah Intl", country: "UAE" },
  { code: "MEL", city: "Melbourne", name: "Melbourne Airport", country: "Australia" },
  { code: "SYD", city: "Sydney", name: "Kingsford Smith", country: "Australia" },
  { code: "LHR", city: "London", name: "Heathrow", country: "UK" },
  { code: "LGW", city: "London", name: "Gatwick", country: "UK" },
  { code: "JFK", city: "New York", name: "JFK", country: "USA" },
  { code: "EWR", city: "Newark", name: "Newark Liberty", country: "USA" },
  { code: "LAX", city: "Los Angeles", name: "LAX", country: "USA" },
  { code: "SFO", city: "San Francisco", name: "SFO", country: "USA" },
  { code: "YYZ", city: "Toronto", name: "Pearson", country: "Canada" },
  { code: "SIN", city: "Singapore", name: "Changi", country: "Singapore" },
  { code: "BKK", city: "Bangkok", name: "Suvarnabhumi", country: "Thailand" },
  { code: "KUL", city: "Kuala Lumpur", name: "KLIA", country: "Malaysia" },
  { code: "DOH", city: "Doha", name: "Hamad Intl", country: "Qatar" },
  { code: "RUH", city: "Riyadh", name: "King Khalid", country: "Saudi Arabia" },
  { code: "JED", city: "Jeddah", name: "King Abdulaziz", country: "Saudi Arabia" },
  { code: "CAI", city: "Cairo", name: "Cairo Intl", country: "Egypt" },
  { code: "IST", city: "Istanbul", name: "Istanbul Airport", country: "Turkey" },
  { code: "CDG", city: "Paris", name: "Charles de Gaulle", country: "France" },
  { code: "FRA", city: "Frankfurt", name: "Frankfurt Airport", country: "Germany" },
  { code: "AMS", city: "Amsterdam", name: "Schiphol", country: "Netherlands" },
  { code: "HKG", city: "Hong Kong", name: "Hong Kong Intl", country: "Hong Kong" },
  { code: "NRT", city: "Tokyo", name: "Narita", country: "Japan" },
  { code: "ICN", city: "Seoul", name: "Incheon", country: "South Korea" },
  { code: "PEK", city: "Beijing", name: "Capital Intl", country: "China" },
  { code: "PVG", city: "Shanghai", name: "Pudong", country: "China" },
];

window.searchAirports = function searchAirports(query, limit = 8) {
  const q = (query || "").trim().toLowerCase();
  if (!q) return [];
  return window.TRAVELAI_AIRPORTS.filter((a) => {
    return (
      a.code.toLowerCase().startsWith(q) ||
      a.city.toLowerCase().includes(q) ||
      a.name.toLowerCase().includes(q) ||
      `${a.city} ${a.country}`.toLowerCase().includes(q)
    );
  }).slice(0, limit);
};
