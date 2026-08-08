import { Alert, Pressable, Switch, Text, TextInput, View } from "react-native";
import {useState} from 'react';
import { router } from "expo-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Card, Screen, s } from "../../components/ui";
import { api } from "../../lib/api";
import type { FillUp, Vehicle } from "../../../../packages/types/src";
import {fillEditSchema,fuels,vehicleEditSchema} from '../../lib/car-validation';
export default function Car() {
  const cache = useQueryClient();
  const [editing,setEditing]=useState<Vehicle>();const [edit,setEdit]=useState<any>();const [detail,setDetail]=useState<FillUp>();const [fillEdit,setFillEdit]=useState<any>();
  const [editError,setEditError]=useState<string>();
  const [stationSearch,setStationSearch]=useState('');const [stationResults,setStationResults]=useState<any[]>([]);
  const vehicles = useQuery({
    queryKey: ["vehicles"],
    queryFn: () => api.get<Vehicle[]>("/vehicles"),
  });
  const vehicle =
    vehicles.data?.find((x) => x.is_primary) ?? vehicles.data?.[0];
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
          <Pressable onPress={()=>{setEditing(item);setEdit({...item})}}><Text>Edit vehicle</Text></Pressable>
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
      {editing&&<Card><Text>Edit {editing.nickname}</Text>{['nickname','make','model','year','variant','registration_plate','tank_capacity_litres'].map(key=><TextInput key={key} placeholder={key} value={String(edit?.[key]??'')} onChangeText={value=>setEdit((current:any)=>({...current,[key]:value}))}/>)}<Text>Fuel type</Text><View style={{flexDirection:'row',flexWrap:'wrap',gap:8}}>{fuels.map(fuel=><Pressable key={fuel} onPress={()=>setEdit((x:any)=>({...x,fuel_type:fuel}))}><Text>{fuel}{edit.fuel_type===fuel?' ✓':''}</Text></Pressable>)}</View><Button label="Save vehicle" onPress={async()=>{const parsed=vehicleEditSchema.safeParse(edit);if(!parsed.success){setEditError(parsed.error.issues[0]?.message);return}await api.patch(`/vehicles/${editing.id}`,parsed.data);setEditing(undefined);setEditError(undefined);await cache.invalidateQueries({queryKey:['vehicles']})}}/><Button label="Cancel" onPress={()=>setEditing(undefined)}/>{editError&&<Text accessibilityRole="alert">{editError}</Text>}</Card>}
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
          onPress={()=>{setDetail(x);setFillEdit({...x})}} onLongPress={() =>
            Alert.alert(
              "Delete fill-up?",
              "This will also remove its active public observation.",
              [
                { text: "Cancel", style: "cancel" },
                {
                  text: "Delete",
                  style: "destructive",
                  onPress: async () => {
                    await api.delete(`/fill-ups/${x.id}`);
                    await cache.invalidateQueries({ queryKey: ["fillups"] });
                  },
                },
              ],
            )
          }
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
              {x.fuel_economy_l_per_100km ?? "Pending"} L/100km
            </Text>
            <Text style={s.muted}>Long press to delete</Text>
          </Card>
        </Pressable>
      ))}
      {detail&&<Card><Text style={s.metric}>Edit fill-up</Text><Text>Station</Text><TextInput placeholder="Search station, city, or address" value={stationSearch} onChangeText={setStationSearch} onSubmitEditing={async()=>setStationResults(await api.get<any[]>(`/fuel-stations/search?q=${encodeURIComponent(stationSearch)}`))}/>{stationResults.map(station=><Pressable key={station.id} onPress={()=>setFillEdit((x:any)=>({...x,station_id:station.id}))}><Text>{station.name} · {station.address_line}{fillEdit.station_id===station.id?' ✓':''}</Text></Pressable>)}<Pressable onPress={()=>setFillEdit((x:any)=>({...x,station_id:null}))}><Text>No station / clear selection</Text></Pressable>{['occurred_at','litres','pump_price_per_litre','discount_amount','total_amount','odometer_km','notes'].map(key=><View key={key}><Text>{key.replaceAll('_',' ')}</Text><TextInput value={String(fillEdit?.[key]??'')} onChangeText={value=>setFillEdit((current:any)=>({...current,[key]:value}))}/></View>)}<Text>Fuel type</Text><View style={{flexDirection:'row',flexWrap:'wrap',gap:8}}>{fuels.map(fuel=><Pressable key={fuel} onPress={()=>setFillEdit((x:any)=>({...x,fuel_type:fuel}))}><Text>{fuel}{fillEdit.fuel_type===fuel?' ✓':''}</Text></Pressable>)}</View><View style={{flexDirection:'row',justifyContent:'space-between'}}><Text>Full tank</Text><Switch value={!!fillEdit?.full_tank} onValueChange={value=>setFillEdit((x:any)=>({...x,full_tank:value}))}/></View><View style={{flexDirection:'row',justifyContent:'space-between'}}><Text>Missed previous fill</Text><Switch value={!!fillEdit?.missed_previous_fill} onValueChange={value=>setFillEdit((x:any)=>({...x,missed_previous_fill:value}))}/></View><Button label="Save fill-up" onPress={async()=>{const parsed=fillEditSchema.safeParse(fillEdit);if(!parsed.success){setEditError(parsed.error.issues[0]?.message);return}await api.patch(`/fill-ups/${detail.id}`,parsed.data);setDetail(undefined);setEditError(undefined);await cache.invalidateQueries({queryKey:['fillups']})}}/><Button label="Delete fill-up" onPress={()=>Alert.alert('Delete fill-up?','This cannot be undone.',[{text:'Cancel',style:'cancel'},{text:'Delete',style:'destructive',onPress:async()=>{await api.delete(`/fill-ups/${detail.id}`);setDetail(undefined);await cache.invalidateQueries({queryKey:['fillups']})}}])}/><Button label="Close" onPress={()=>setDetail(undefined)}/>{editError&&<Text accessibilityRole="alert">{editError}</Text>}</Card>}
    </Screen>
  );
}
