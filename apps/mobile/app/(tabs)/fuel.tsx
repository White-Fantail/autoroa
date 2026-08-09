import { useRef, useState } from "react";
import {
  Linking,
  Modal,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import * as Location from "expo-location";
import { useQuery } from "@tanstack/react-query";
import { Button, Card, Screen, s } from "../../components/ui";
import { FuelMap } from "../../components/FuelMap";
import { api } from "../../lib/api";
import { freshness } from "../../../../packages/config/src";
import type { FuelType, NearbyPrice } from "../../../../packages/types/src";

type DisplayPrice = Omit<NearbyPrice, "distance_km"> & { distance_km?: number };

type StationResult = NearbyPrice["station"] & {
  current_prices?: DisplayPrice[];
};

type SearchStation = {
  id: string;
  name: string;
  address_line: string;
  latitude: string;
  longitude: string;
};

type CurrentStationPrice = {
  station_id: string;
  fuel_type: FuelType;
  price: string;
  observed_at: string;
  verification_level: string;
  confidence_score: string;
};

const fuelTypes: Array<{ value: FuelType; label: string }> = [
  { value: "PETROL_91", label: "91" },
  { value: "PETROL_95", label: "95" },
  { value: "PETROL_98", label: "98" },
  { value: "DIESEL", label: "Diesel" },
];

export default function Fuel() {
  const [fuel, setFuel] = useState<FuelType>("PETROL_91");
  const [sort, setSort] = useState<"distance" | "price">("distance");
  const [search, setSearch] = useState("");
  const [searchResults, setSearchResults] = useState<StationResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [searchAttempted, setSearchAttempted] = useState(false);
  const [searchError, setSearchError] = useState(false);
  const [selected, setSelected] = useState<StationResult>();
  const searchRequestId = useRef(0);

  async function runSearch() {
    const query = search.trim();
    if (query.length < 2) return;
    const requestId = ++searchRequestId.current;
    setSearching(true);
    setSearchAttempted(true);
    setSearchError(false);
    try {
      const rows = await api.get<SearchStation[]>(
        `/fuel-stations/search?q=${encodeURIComponent(query)}`,
      );
      const results = await Promise.all(
        rows.map(async (searchStation): Promise<StationResult> => {
          const station: NearbyPrice["station"] = {
            id: searchStation.id,
            name: searchStation.name,
            address: searchStation.address_line,
            latitude: searchStation.latitude,
            longitude: searchStation.longitude,
          };
          const currentPrices = await api.get<CurrentStationPrice[]>(
            `/fuel-stations/${station.id}/prices`,
          );
          return {
            ...station,
            current_prices: currentPrices.map((price): DisplayPrice => ({
              station,
              fuel_type: price.fuel_type,
              price: price.price,
              observed_at: price.observed_at,
              verification_level: price.verification_level,
              confidence: price.confidence_score,
            })),
          };
        }),
      );
      if (requestId === searchRequestId.current) setSearchResults(results);
    } catch {
      if (requestId === searchRequestId.current) {
        setSearchError(true);
        setSearchResults([]);
      }
    } finally {
      if (requestId === searchRequestId.current) setSearching(false);
    }
  }

  function updateSearch(value: string) {
    searchRequestId.current += 1;
    setSearch(value);
    setSearching(false);
    setSearchAttempted(false);
    setSearchError(false);
    setSearchResults([]);
  }

  const location = useQuery({
    queryKey: ["location"],
    queryFn: async () => {
      const permission = await Location.requestForegroundPermissionsAsync();
      if (!permission.granted) throw new Error("Location permission declined");
      return Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
    },
  });
  const prices = useQuery({
    queryKey: [
      "prices",
      location.data?.coords.latitude,
      location.data?.coords.longitude,
      fuel,
      sort,
    ],
    queryFn: () =>
      api.get<NearbyPrice[]>(
        `/fuel-prices/nearby?latitude=${location.data!.coords.latitude}&longitude=${location.data!.coords.longitude}&radius_km=15&fuel_type=${fuel}&sort=${sort}`,
      ),
    enabled: !!location.data,
  });

  const visibleSearchResults = searchResults.filter((station) =>
    station.current_prices?.some((price) => price.fuel_type === fuel),
  );
  const resultCount = prices.data?.length ?? 0;

  return (
    <Screen title="Fuel near you">
      <View style={styles.mapWrap}>
        {location.data ? (
          <FuelMap
            latitude={location.data.coords.latitude}
            longitude={location.data.coords.longitude}
            prices={prices.data ?? []}
            onSelect={(price) =>
              setSelected({ ...price.station, current_prices: [price] })
            }
          />
        ) : (
          <View style={styles.mapPlaceholder}>
            <View style={styles.locationIcon}><Text style={styles.locationIconText}>⌖</Text></View>
            <Text style={styles.emptyTitle}>
              {location.isError ? "Find fuel without location" : "Finding stations near you"}
            </Text>
            <Text style={styles.emptyCopy}>
              {location.isError
                ? "Search by suburb, city, or station name below."
                : "We only use your location while you are on this screen."}
            </Text>
            {location.isLoading && <Text style={styles.loadingLabel}>Locating…</Text>}
            {location.isError && (
              <Pressable accessibilityRole="button" onPress={() => location.refetch()}>
                <Text style={s.link}>Try location again</Text>
              </Pressable>
            )}
          </View>
        )}
        {location.data && prices.isSuccess && (
          <View style={styles.mapBadge}>
            <Text style={styles.mapBadgeText}>{resultCount} nearby</Text>
          </View>
        )}
      </View>

      <View style={styles.controls}>
        <Text style={styles.controlLabel}>Fuel type</Text>
        <View accessibilityRole="radiogroup" style={styles.segmentedControl}>
          {fuelTypes.map((item) => {
            const active = fuel === item.value;
            return (
              <Pressable
                key={item.value}
                accessibilityRole="radio"
                accessibilityState={{ checked: active }}
                onPress={() => setFuel(item.value)}
                style={[styles.segment, active && styles.segmentActive]}
              >
                <Text style={[styles.segmentText, active && styles.segmentTextActive]}>
                  {item.label}
                </Text>
              </Pressable>
            );
          })}
        </View>
      </View>

      <View style={styles.resultHeader}>
        <View>
          <Text style={styles.sectionTitle}>Nearby prices</Text>
          <Text style={s.muted}>
            {prices.isLoading
              ? "Updating prices…"
              : prices.isError
                ? "Price update failed"
                : location.data && prices.isSuccess
                  ? `${resultCount} stations within 15 km`
                  : "Location needed for nearby prices"}
          </Text>
        </View>
        <View accessibilityRole="radiogroup" style={styles.sortControl}>
          {(["distance", "price"] as const).map((option) => {
            const active = sort === option;
            return (
              <Pressable
                key={option}
                accessibilityRole="radio"
                accessibilityState={{ checked: active }}
                onPress={() => setSort(option)}
                style={[styles.sortOption, active && styles.sortOptionActive]}
              >
                <Text style={[styles.sortText, active && styles.sortTextActive]}>
                  {option === "distance" ? "Nearest" : "Cheapest"}
                </Text>
              </Pressable>
            );
          })}
        </View>
      </View>

      {prices.isError && (
        <Card>
          <Text style={styles.cardTitle}>Prices unavailable</Text>
          <Text style={s.muted}>We could not refresh nearby prices.</Text>
          <Pressable accessibilityRole="button" onPress={() => prices.refetch()}>
            <Text style={s.link}>Try again</Text>
          </Pressable>
        </Card>
      )}
      {location.data && prices.isSuccess && !prices.data.length && (
        <View style={styles.emptyResults}>
          <Text style={styles.emptyResultsIcon}>⛽</Text>
          <Text style={styles.emptyTitle}>No recent {fuelLabel(fuel)} prices nearby</Text>
          <Text style={styles.emptyCopy}>
            Try another fuel type or search a different area below.
          </Text>
        </View>
      )}
      {prices.data?.map((price) => (
        <PriceCard
          key={price.station.id}
          price={price}
          onView={() => setSelected({ ...price.station, current_prices: [price] })}
        />
      ))}

      <View style={styles.searchSection}>
        <Text style={styles.sectionTitle}>Search another area</Text>
        <Text style={s.muted}>Find a station, suburb, city, or address.</Text>
        <View style={styles.searchRow}>
          <TextInput
            accessibilityLabel="Search station or area"
            placeholder="e.g. Christchurch"
            placeholderTextColor="#718582"
            returnKeyType="search"
            value={search}
            onChangeText={updateSearch}
            onSubmitEditing={runSearch}
            style={styles.searchInput}
          />
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Search"
            disabled={search.trim().length < 2 || searching}
            onPress={runSearch}
            style={[styles.searchButton, (search.trim().length < 2 || searching) && s.disabled]}
          >
            <Text style={styles.searchButtonText}>{searching ? "…" : "Search"}</Text>
          </Pressable>
        </View>
        {search.length > 0 && search.trim().length < 2 && (
          <Text style={s.muted}>Enter at least 2 characters to search.</Text>
        )}
        {searchError && !searching && (
          <View style={styles.searchFeedback}>
            <Text style={styles.searchError}>We could not search for stations.</Text>
            <Pressable accessibilityRole="button" onPress={runSearch}>
              <Text style={s.link}>Try again</Text>
            </Pressable>
          </View>
        )}
        {searchAttempted && !searching && !searchError && !visibleSearchResults.length && (
          <Text style={s.muted}>No matching stations with {fuelLabel(fuel)} prices.</Text>
        )}
      </View>

      {visibleSearchResults.map((station) => {
        const price = station.current_prices!.find((item) => item.fuel_type === fuel)!;
        return (
          <PriceCard
            key={station.id}
            price={{ ...price, station }}
            onView={() => setSelected(station)}
          />
        );
      })}

      <StationSheet station={selected} onClose={() => setSelected(undefined)} />
    </Screen>
  );
}

function PriceCard({ price, onView }: { price: DisplayPrice; onView: () => void }) {
  return (
    <Card>
      <View style={styles.cardTopRow}>
        <View style={styles.cardIdentity}>
          <Text style={styles.cardTitle} numberOfLines={1}>{price.station.name}</Text>
          <Text style={s.muted}>{price.distance_km != null ? `${price.distance_km} km away` : price.station.address}</Text>
        </View>
        <View style={styles.priceBlock}>
          <Text style={styles.price}>${price.price}</Text>
          <Text style={styles.perLitre}>per litre</Text>
        </View>
      </View>
      <View style={styles.metaRow}>
        <Text style={styles.fuelBadge}>{fuelLabel(price.fuel_type)}</Text>
        <Text style={price.verification_level === "VERIFIED_RECEIPT" ? styles.verified : s.muted}>
          {price.verification_level === "VERIFIED_RECEIPT" ? "✓ Verified" : "User confirmed"}
        </Text>
        <Text style={s.muted}>· {freshness(price.observed_at)}</Text>
      </View>
      <View style={styles.cardActions}>
        <Pressable accessibilityRole="button" onPress={onView} style={styles.secondaryButton}>
          <Text style={styles.secondaryButtonText}>Details</Text>
        </Pressable>
        <Pressable
          accessibilityRole="button"
          onPress={() => openDirections(price.station.latitude, price.station.longitude)}
          style={styles.directionButton}
        >
          <Text style={styles.directionButtonText}>Directions ↗</Text>
        </Pressable>
      </View>
    </Card>
  );
}

function StationSheet({ station, onClose }: { station?: StationResult; onClose: () => void }) {
  return (
    <Modal visible={!!station} transparent animationType="slide" onRequestClose={onClose}>
      <View style={styles.modalRoot}>
        <Pressable
          accessibilityElementsHidden
          importantForAccessibility="no-hide-descendants"
          style={styles.backdrop}
          onPress={onClose}
        />
        {station && (
          <View accessibilityViewIsModal style={styles.sheet}>
            <View style={styles.sheetHandle} />
            <View style={styles.sheetTitleRow}>
              <View style={styles.cardIdentity}>
                <Text accessibilityRole="header" style={styles.sheetTitle}>{station.name}</Text>
                <Text style={s.muted}>{station.address}</Text>
              </View>
              <Pressable accessibilityRole="button" accessibilityLabel="Close station details" onPress={onClose} style={styles.closeButton}>
                <Text style={styles.closeText}>×</Text>
              </Pressable>
            </View>
            {station.current_prices?.map((price) => (
              <View key={`${price.fuel_type}-${price.observed_at}`} style={styles.sheetPriceRow}>
                <Text style={styles.cardTitle}>{fuelLabel(price.fuel_type)}</Text>
                <Text style={styles.sheetPrice}>${price.price}/L</Text>
                <Text style={s.muted}>{freshness(price.observed_at)}</Text>
              </View>
            ))}
            <Button label="Get directions" onPress={() => openDirections(station.latitude, station.longitude)} />
          </View>
        )}
      </View>
    </Modal>
  );
}

function fuelLabel(fuel: FuelType) {
  return fuel === "DIESEL" ? "Diesel" : fuel.replace("PETROL_", "Unleaded ");
}

function openDirections(latitude: number | string, longitude: number | string) {
  return Linking.openURL(
    `https://www.google.com/maps/dir/?api=1&destination=${latitude},${longitude}`,
  );
}

const styles = StyleSheet.create({
  mapWrap: { position: "relative" },
  mapPlaceholder: { minHeight: 238, borderRadius: 20, backgroundColor: "#E2F0ED", alignItems: "center", justifyContent: "center", padding: 28, gap: 8 },
  locationIcon: { width: 52, height: 52, borderRadius: 26, backgroundColor: "#C7E7DF", alignItems: "center", justifyContent: "center", marginBottom: 4 },
  locationIconText: { color: "#087E6B", fontSize: 28, fontWeight: "800" },
  loadingLabel: { color: "#087E6B", fontWeight: "700", marginTop: 4 },
  mapBadge: { position: "absolute", left: 12, top: 12, borderRadius: 999, backgroundColor: "rgba(16,42,46,0.88)", paddingHorizontal: 12, paddingVertical: 7 },
  mapBadgeText: { color: "white", fontWeight: "700", fontSize: 13 },
  controls: { gap: 8 },
  controlLabel: { color: "#405A5D", fontSize: 13, fontWeight: "700" },
  segmentedControl: { flexDirection: "row", borderRadius: 14, backgroundColor: "#E7EFED", padding: 4, gap: 3 },
  segment: { flex: 1, minHeight: 42, borderRadius: 11, alignItems: "center", justifyContent: "center", paddingHorizontal: 4 },
  segmentActive: { backgroundColor: "#FFFFFF", shadowColor: "#102A2E", shadowOffset: { width: 0, height: 1 }, shadowOpacity: 0.1, shadowRadius: 4, elevation: 2 },
  segmentText: { color: "#587074", fontWeight: "700" },
  segmentTextActive: { color: "#087E6B" },
  resultHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: 12, marginTop: 2 },
  sectionTitle: { fontSize: 20, fontWeight: "800", color: "#102A2E" },
  sortControl: { flexDirection: "row", backgroundColor: "#E7EFED", borderRadius: 10, padding: 3 },
  sortOption: { paddingHorizontal: 9, paddingVertical: 7, borderRadius: 8 },
  sortOptionActive: { backgroundColor: "#FFFFFF" },
  sortText: { color: "#587074", fontWeight: "700", fontSize: 12 },
  sortTextActive: { color: "#102A2E" },
  emptyResults: { alignItems: "center", paddingVertical: 26, paddingHorizontal: 20, gap: 7 },
  emptyResultsIcon: { fontSize: 30 },
  emptyTitle: { color: "#102A2E", fontSize: 18, fontWeight: "800", textAlign: "center" },
  emptyCopy: { color: "#587074", lineHeight: 20, textAlign: "center" },
  cardTopRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start", gap: 12 },
  cardIdentity: { flex: 1, gap: 3 },
  cardTitle: { color: "#102A2E", fontSize: 18, fontWeight: "800" },
  priceBlock: { alignItems: "flex-end" },
  price: { color: "#087E6B", fontSize: 25, fontWeight: "800" },
  perLitre: { color: "#718582", fontSize: 11 },
  metaRow: { flexDirection: "row", alignItems: "center", flexWrap: "wrap", gap: 6 },
  fuelBadge: { color: "#405A5D", backgroundColor: "#E7EFED", borderRadius: 6, paddingHorizontal: 7, paddingVertical: 4, overflow: "hidden", fontSize: 12, fontWeight: "700" },
  verified: { color: "#087E6B", fontWeight: "700" },
  cardActions: { flexDirection: "row", gap: 10, marginTop: 4 },
  secondaryButton: { flex: 1, minHeight: 42, borderWidth: 1.5, borderColor: "#A9BFBA", borderRadius: 12, alignItems: "center", justifyContent: "center" },
  secondaryButtonText: { color: "#405A5D", fontWeight: "700" },
  directionButton: { flex: 1, minHeight: 42, backgroundColor: "#16A085", borderRadius: 12, alignItems: "center", justifyContent: "center" },
  directionButtonText: { color: "white", fontWeight: "700" },
  searchSection: { borderTopWidth: 1, borderTopColor: "#D4E2DF", paddingTop: 18, gap: 7, marginTop: 2 },
  searchRow: { flexDirection: "row", gap: 8, marginTop: 4 },
  searchInput: { flex: 1, minWidth: 0, minHeight: 48, borderWidth: 1.5, borderColor: "#7E9591", borderRadius: 12, backgroundColor: "#FFFFFF", paddingHorizontal: 12, fontSize: 16, color: "#102A2E" },
  searchButton: { minHeight: 48, borderRadius: 12, backgroundColor: "#102A2E", alignItems: "center", justifyContent: "center", paddingHorizontal: 15 },
  searchButtonText: { color: "white", fontWeight: "700" },
  searchFeedback: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 12 },
  searchError: { color: "#B42318", flex: 1 },
  modalRoot: { flex: 1, justifyContent: "flex-end" },
  backdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: "rgba(16,42,46,0.38)" },
  sheet: { backgroundColor: "#F6FAF9", borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: 20, paddingBottom: 28, gap: 16 },
  sheetHandle: { width: 42, height: 4, borderRadius: 2, backgroundColor: "#B8C9C5", alignSelf: "center" },
  sheetTitleRow: { flexDirection: "row", alignItems: "flex-start", gap: 12 },
  sheetTitle: { color: "#102A2E", fontSize: 23, fontWeight: "800" },
  closeButton: { width: 40, height: 40, borderRadius: 20, backgroundColor: "#E7EFED", alignItems: "center", justifyContent: "center" },
  closeText: { color: "#405A5D", fontSize: 25, lineHeight: 27 },
  sheetPriceRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 8, borderBottomWidth: 1, borderBottomColor: "#D4E2DF", paddingBottom: 12 },
  sheetPrice: { color: "#087E6B", fontSize: 18, fontWeight: "800" },
});
