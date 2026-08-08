import { useState } from "react";
import { Linking, Pressable, Text, TextInput } from "react-native";
import * as Location from "expo-location";
import { useQuery } from "@tanstack/react-query";
import { Card, Screen, s } from "../../components/ui";
import { api } from "../../lib/api";
import { freshness } from "../../../../packages/config/src";
import type { FuelType, NearbyPrice } from "../../../../packages/types/src";
import {FuelMap} from '../../components/FuelMap';
export default function Fuel() {
  const [fuel, setFuel] = useState<FuelType>("PETROL_91");
  const [sort, setSort] = useState("distance");
  const [search,setSearch]=useState("");const [searchResults,setSearchResults]=useState<any[]>([]);
  const [selected,setSelected]=useState<any>();
  async function runSearch(){const rows=await api.get<any[]>(`/fuel-stations/search?q=${encodeURIComponent(search)}`);setSearchResults(await Promise.all(rows.map(async station=>({...station,current_prices:await api.get<any[]>(`/fuel-stations/${station.id}/prices`)}))));}
  const location = useQuery({
    queryKey: ["location"],
    queryFn: async () => {
      const permission = await Location.requestForegroundPermissionsAsync();
      if (!permission.granted) throw new Error("Location permission declined");
      return Location.getCurrentPositionAsync({
        accuracy: Location.Accuracy.Balanced,
      });
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
  return (
    <Screen title="Fuel near you">
      {location.data&&<FuelMap latitude={location.data.coords.latitude} longitude={location.data.coords.longitude} prices={prices.data??[]} onSelect={price=>setSelected({...price.station,current_prices:[price]})}/>} 
      {(location.isLoading||prices.isLoading)&&<Text>Loading nearby stations…</Text>}
      {prices.isError&&<Pressable onPress={()=>prices.refetch()}><Text>Could not load prices. Tap to retry.</Text></Pressable>}
      {!prices.isLoading&&location.data&&!prices.data?.length&&<Text>No recent prices were found nearby.</Text>}
      <Text>Location is only used while finding nearby stations.</Text>
      {(["PETROL_91", "PETROL_95", "PETROL_98", "DIESEL"] as FuelType[]).map(
        (x) => (
          <Pressable key={x} onPress={() => setFuel(x)}>
            <Text>{x.replace("PETROL_", "")}</Text>
          </Pressable>
        ),
      )}
      <Pressable
        onPress={() => setSort((x) => (x === "price" ? "distance" : "price"))}
      >
        <Text>Sort: {sort}</Text>
      </Pressable>
      {location.isError && (
        <><Text>Location is optional. Search by station, city, or address.</Text><TextInput placeholder="Christchurch or station name" value={search} onChangeText={setSearch} onSubmitEditing={runSearch}/>{!searchResults.length&&search.length>0&&<Text>No matching stations yet. Press search on the keyboard.</Text>}{searchResults.map(station=><Card key={station.id}><Text>{station.name}</Text><Text>{station.address_line}</Text>{station.current_prices?.filter((price:any)=>price.fuel_type===fuel).map((price:any)=><Text key={price.id} style={s.metric}>${price.price}/L · {freshness(price.observed_at)} · {price.verification_level==='VERIFIED_RECEIPT'?'Verified':'User confirmed'}</Text>)}<Pressable onPress={()=>setSelected(station)}><Text>View station</Text></Pressable><Pressable onPress={()=>Linking.openURL(`https://www.google.com/maps/dir/?api=1&destination=${station.latitude},${station.longitude}`)}><Text>Directions</Text></Pressable></Card>)}</>
      )}
      {prices.data?.map((x) => (
        <Card key={x.station.id}>
          <Text style={{ fontSize: 20, fontWeight: "700" }}>
            {x.station.name}
          </Text>
          <Text style={s.metric}>${x.price}/L</Text>
          <Text>
            {x.verification_level === "VERIFIED_RECEIPT"
              ? "✓ Verified"
              : "User confirmed"}{" "}
            · {freshness(x.observed_at)}
          </Text>
          <Text style={s.muted}>{x.distance_km} km away</Text>
          <Pressable onPress={()=>setSelected({...x.station,current_prices:[x]})}><Text>View station</Text></Pressable>
          <Pressable onPress={()=>Linking.openURL(`https://www.google.com/maps/dir/?api=1&destination=${x.station.latitude},${x.station.longitude}`)}><Text>Directions</Text></Pressable>
        </Card>
      ))}
      {selected&&<Card><Text style={{fontSize:22,fontWeight:'700'}}>{selected.name}</Text><Text>{selected.address_line??selected.address}</Text>{selected.current_prices?.map((price:any)=><Text key={price.id??price.fuel_type}>{price.fuel_type}: ${price.price}/L · {freshness(price.observed_at)}</Text>)}<Pressable onPress={()=>setSelected(undefined)}><Text>Close</Text></Pressable></Card>}
    </Screen>
  );
}
