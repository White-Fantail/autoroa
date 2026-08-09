import { Pressable, StyleSheet, Text, View } from "react-native";
import type { NearbyPrice } from "../../../packages/types/src";

export function FuelMap({
  prices,
  onSelect,
}: {
  latitude: number;
  longitude: number;
  prices: NearbyPrice[];
  onSelect?: (price: NearbyPrice) => void;
}) {
  return (
    <View style={styles.map}>
      <View style={styles.mapPattern} />
      {prices.length ? (
        <View style={styles.markers}>
          {prices.slice(0, 4).map((price) => (
            <Pressable
              key={price.station.id}
              accessibilityRole="button"
              accessibilityLabel={`${price.station.name}, $${price.price} per litre`}
              onPress={() => onSelect?.(price)}
              style={styles.marker}
            >
              <Text style={styles.markerText}>${price.price}</Text>
            </Pressable>
          ))}
        </View>
      ) : (
        <View style={styles.empty}>
          <Text style={styles.emptyTitle}>No price markers yet</Text>
          <Text style={styles.emptyCopy}>The interactive map is available in the mobile app.</Text>
        </View>
      )}
      <Text style={styles.webLabel}>Map preview</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  map: { minHeight: 238, borderRadius: 20, overflow: "hidden", backgroundColor: "#DDEBE8", alignItems: "center", justifyContent: "center" },
  mapPattern: { position: "absolute", width: "75%", height: "140%", borderWidth: 24, borderColor: "rgba(255,255,255,0.55)", borderRadius: 90, transform: [{ rotate: "24deg" }] },
  markers: { width: "78%", flexDirection: "row", flexWrap: "wrap", justifyContent: "space-around", gap: 30 },
  marker: { backgroundColor: "#102A2E", borderRadius: 18, borderBottomLeftRadius: 4, paddingHorizontal: 11, paddingVertical: 8, shadowColor: "#102A2E", shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.2, shadowRadius: 4 },
  markerText: { color: "white", fontWeight: "800", fontSize: 13 },
  empty: { alignItems: "center", gap: 5, padding: 28 },
  emptyTitle: { color: "#102A2E", fontSize: 17, fontWeight: "800" },
  emptyCopy: { color: "#587074", textAlign: "center" },
  webLabel: { position: "absolute", right: 10, bottom: 9, color: "#587074", fontSize: 10, fontWeight: "700", textTransform: "uppercase" },
});
