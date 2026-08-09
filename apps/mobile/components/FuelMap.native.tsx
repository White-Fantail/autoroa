import { StyleSheet } from "react-native";
import MapView, { Marker } from "react-native-maps";
import type { NearbyPrice } from "../../../packages/types/src";
import { freshness } from "../../../packages/config/src";

export function FuelMap({ latitude, longitude, prices, onSelect }: { latitude: number; longitude: number; prices: NearbyPrice[]; onSelect?: (price: NearbyPrice) => void }) {
  return (
    <MapView
      style={styles.map}
      initialRegion={{ latitude, longitude, latitudeDelta: 0.12, longitudeDelta: 0.12 }}
      showsUserLocation
      showsMyLocationButton
    >
      {prices.map((item) => (
        <Marker
          key={item.station.id}
          coordinate={{ latitude: Number(item.station.latitude), longitude: Number(item.station.longitude) }}
          title={`${item.station.name} · $${item.price}/L`}
          description={`${freshness(item.observed_at)} · ${item.verification_level}`}
          onPress={() => onSelect?.(item)}
        />
      ))}
    </MapView>
  );
}

const styles = StyleSheet.create({ map: { height: 280, borderRadius: 20, overflow: "hidden" } });
