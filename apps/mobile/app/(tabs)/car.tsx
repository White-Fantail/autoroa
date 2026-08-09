import { useEffect, useState } from "react";
import { Alert, Pressable, ScrollView, Text, View } from "react-native";
import { router } from "expo-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Card, Screen, s } from "../../components/ui";
import { api } from "../../lib/api";
import type { FillUp, Vehicle } from "../../../../packages/types/src";
import {fuelEconomyText} from '../../lib/fuel-economy';
import {chooseVehicle,fillUpEditRoute,vehicleEditRoute} from '../../lib/workflow';
export default function Car() {
  const cache = useQueryClient();
  const [selectedVehicleId, setSelectedVehicleId] = useState<string>();
  const vehicles = useQuery({
    queryKey: ["vehicles"],
    queryFn: () => api.get<Vehicle[]>("/vehicles"),
  });
  const vehicle = chooseVehicle(vehicles.data ?? [], selectedVehicleId);
  useEffect(() => {
    if (vehicle && vehicle.id !== selectedVehicleId) {
      setSelectedVehicleId(vehicle.id);
    }
  }, [selectedVehicleId, vehicle]);
  const history = useQuery({
    queryKey: ["fillups", vehicle?.id],
    queryFn: () => api.get<FillUp[]>(`/fill-ups?vehicle_id=${vehicle!.id}`),
    enabled: !!vehicle,
  });
  const metrics=useQuery({queryKey:['car-metrics',vehicle?.id],queryFn:()=>api.get<any>(`/vehicles/${vehicle!.id}/metrics?period=12m`),enabled:!!vehicle});
  const months=Object.entries((history.data??[]).reduce<Record<string,number>>((totals,fill)=>{const month=fill.occurred_at.slice(0,7);totals[month]=(totals[month]??0)+Number(fill.total_amount);return totals},{})).sort(([a],[b])=>a.localeCompare(b)).slice(-12);
  return (
    <Screen title="My Car">
      <Text>Overview　Fill-ups　Economy　Costs　Vehicle</Text>
      {!!vehicles.data?.length && (
        <View style={{gap:8}}>
          <Text style={s.muted}>Viewing vehicle</Text>
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={{gap:8}}
          >
            {vehicles.data.map((item) => {
              const selected = item.id === vehicle?.id;
              return (
                <Pressable
                  key={item.id}
                  accessibilityRole="button"
                  accessibilityState={{selected}}
                  accessibilityLabel={`View ${item.nickname}`}
                  onPress={() => setSelectedVehicleId(item.id)}
                  style={[s.choice, selected && s.choiceSelected]}
                >
                  <Text style={{fontWeight:selected?'700':'400',color:'#102A2E'}}>
                    {item.nickname}{item.is_primary ? " · Primary" : ""}
                  </Text>
                  <Text style={s.muted}>{item.make} {item.model}</Text>
                </Pressable>
              );
            })}
          </ScrollView>
        </View>
      )}
      <View style={{flexDirection:'row',gap:8}}><Card><Text style={s.muted}>ECONOMY</Text><Text style={s.metric}>{metrics.data?.average_fuel_economy_l_per_100km??'—'}</Text><Text>L/100km</Text></Card><Card><Text style={s.muted}>12M COST</Text><Text style={s.metric}>${metrics.data?.fuel_spend??'—'}</Text></Card></View>
      <Text>Economy trend</Text><View style={{flexDirection:'row',alignItems:'flex-end',height:80,gap:5}}>{history.data?.slice(0,12).reverse().map(fill=><View key={fill.id} style={{width:12,height:Math.min(75,Number(fill.fuel_economy_l_per_100km??0)*7),backgroundColor:'#16A085'}}/>)}</View>
      <Text>Monthly spend</Text><View style={{flexDirection:'row',alignItems:'flex-end',height:80,gap:5}}>{months.map(([month,total])=><View key={month} accessibilityLabel={`${month}: $${total.toFixed(2)}`} style={{width:16,height:Math.min(75,total/3),backgroundColor:'#9A6700'}}/>)}</View>
      <Text>Price per litre</Text><View style={{flexDirection:'row',alignItems:'flex-end',height:80,gap:5}}>{history.data?.slice(0,12).reverse().map(fill=><View key={fill.id} accessibilityLabel={`${fill.pump_price_per_litre} per litre`} style={{width:12,height:Math.min(75,Number(fill.pump_price_per_litre??0)*25),backgroundColor:'#345995'}}/>)}</View>
      <Button
        label="Add vehicle"
        onPress={() => router.push("/onboarding/vehicle")}
      />
      {vehicles.data?.map((item) => (
        <Card key={item.id}>
          <Text>
            {item.nickname} · {item.make} {item.model}
          </Text>
          {!item.is_primary && (
            <Pressable
              onPress={async () => {
                await api.patch(`/vehicles/${item.id}`, { is_primary: true });
                await cache.invalidateQueries({ queryKey: ["vehicles"] });
              }}
            >
              <Text>Make primary</Text>
            </Pressable>
          )}
          <Pressable accessibilityRole="link" onPress={()=>router.push(vehicleEditRoute(item.id) as any)}><Text style={s.link}>Edit vehicle →</Text></Pressable>
          <Pressable
            onPress={() =>
              Alert.alert(
                "Archive vehicle?",
                `${item.nickname} will leave the active garage.`,
                [
                  { text: "Cancel", style: "cancel" },
                  {
                    text: "Archive",
                    style: "destructive",
                    onPress: async () => {
                      await api.delete(`/vehicles/${item.id}`);
                      await cache.invalidateQueries({ queryKey: ["vehicles"] });
                    },
                  },
                ],
              )
            }
          >
            <Text>Archive</Text>
          </Pressable>
        </Card>
      ))}
      {history.isError && (
        <Text>
          History could not be loaded. Your captured form has not been cleared.
        </Text>
      )}
      {!history.isLoading && !history.data?.length && (
        <Text>No fill-ups yet. Tap + after your next fuel stop.</Text>
      )}
      {history.data?.map((x) => (
        <Pressable
          key={x.id}
          onPress={()=>router.push(fillUpEditRoute(x.id) as any)}
        >
          <Card>
            <Text style={s.muted}>
              {new Date(x.occurred_at).toLocaleDateString("en-NZ")}
            </Text>
            <Text style={{ fontSize: 20 }}>
              {x.litres} L　${x.total_amount}
            </Text>
            <Text>
              {x.pump_price_per_litre ?? "—"}/L ·{" "}
              {fuelEconomyText(x)}
            </Text>
            <Text style={s.link}>Edit fill-up →</Text>
          </Card>
        </Pressable>
      ))}
    </Screen>
  );
}
