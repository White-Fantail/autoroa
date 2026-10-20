import { Pressable, Text, View } from "react-native";
import { router } from "expo-router";
import { useQuery } from "@tanstack/react-query";
import { Card, Screen, s } from "../../components/ui";
import CaptureOutboxCard from "../../components/CaptureOutboxCard";
import { api } from "../../lib/api";
import type { Vehicle } from "../../../../packages/types/src";
import type {FillUp} from '../../../../packages/types/src';
import type {NearbyPrice} from '../../../../packages/types/src';import * as Location from 'expo-location';import {freshness} from '../../../../packages/config/src';
export default function Home() {
  const vehicles = useQuery({
    queryKey: ["vehicles"],
    queryFn: () => api.get<Vehicle[]>("/vehicles"),
  });
  const primary =
    vehicles.data?.find((x) => x.is_primary) ?? vehicles.data?.[0];
  const metrics = useQuery({
    queryKey: ["metrics", primary?.id],
    queryFn: () => api.get<any>(`/vehicles/${primary!.id}/metrics?period=30d`),
    enabled: !!primary,
  });
  const lastFill=useQuery({queryKey:['home-last-fill',primary?.id],queryFn:()=>api.get<FillUp[]>(`/fill-ups?vehicle_id=${primary!.id}&limit=1`),enabled:!!primary});
  const recentCaptures=useQuery({queryKey:['home-capture-recent'],queryFn:()=>api.get<Array<{id:string;status:string;created_at:string}>>('/quick-captures'),refetchInterval:15000});
  const nearby=useQuery({queryKey:['home-nearby'],queryFn:async()=>{const permission=await Location.getForegroundPermissionsAsync();if(!permission.granted)return [];const location=await Location.getCurrentPositionAsync({accuracy:Location.Accuracy.Balanced});return api.get<NearbyPrice[]>(`/fuel-prices/nearby?latitude=${location.coords.latitude}&longitude=${location.coords.longitude}&radius_km=15&fuel_type=${primary?.fuel_type??'PETROL_91'}&sort=price`)},enabled:!!primary});
  return (
    <Screen title="Good morning">
      {vehicles.isError ? (
        <Text>Could not load your garage. Pull to retry.</Text>
      ) : !primary ? (
        <Card>
          <Text>Add your first vehicle to begin.</Text>
        </Card>
      ) : (
        <Card>
          <Text style={s.muted}>PRIMARY VEHICLE</Text>
          <Text style={{ fontSize: 22, fontWeight: "700" }}>
            {primary.nickname}
          </Text>
          <Text style={s.muted}>This month</Text>
          <Text style={s.metric}>{metrics.data?.distance_km ?? "—"} km</Text>
          <Text>
            {metrics.data?.average_fuel_economy_l_per_100km ?? "—"} L/100km · $
            {metrics.data?.fuel_spend ?? "—"} fuel
          </Text>
        </Card>
      )}
      <Card><Text style={{fontSize:17,fontWeight:"700",marginBottom:8}}>Quick Capture</Text><View style={{flexDirection:"row",gap:12}}><Pressable accessibilityRole="button" style={{flex:1,backgroundColor:"#175D4D",borderRadius:12,padding:16}} onPress={()=>router.push("/quick-capture?mode=receipt")}><Text style={{color:"white",fontWeight:"700",textAlign:"center"}}>Scan receipt</Text></Pressable><Pressable accessibilityRole="button" style={{flex:1,backgroundColor:"#E7F4F0",borderRadius:12,padding:16}} onPress={()=>router.push("/quick-capture?mode=full")}><Text style={{color:"#145243",fontWeight:"700",textAlign:"center"}}>Receipt + km</Text></Pressable></View><Text style={s.muted}>One shutter to capture; the app handles syncing.</Text></Card>
      <Pressable accessibilityRole="button" onPress={() => router.push("/quick-actions" as any)}><Text style={s.link}>Set up iPhone Shortcuts & one-tap Home Screen entry →</Text></Pressable>
      <CaptureOutboxCard />
      {recentCaptures.data?.length? <Card><Text style={{fontSize:17,fontWeight:"700",marginBottom:8}}>Recent captures</Text>{recentCaptures.data.slice(0,4).map(item=><Pressable key={item.id} accessibilityRole="button" disabled={!['REVIEW_REQUIRED','FAILED'].includes(item.status)} onPress={()=>router.push(`/capture-review/${item.id}` as any)} style={{paddingVertical:10,borderBottomWidth:1,borderColor:"#E4EBE8"}}><Text style={{fontWeight:"600"}}>{item.status==='CONFIRMED'?'✓ Saved':item.status==='REVIEW_REQUIRED'||item.status==='FAILED'?'Needs review ›':'Processing…'}</Text><Text style={s.muted}>{new Date(item.created_at).toLocaleString('en-NZ')}</Text></Pressable>)}</Card>:null}
      {lastFill.data?.[0]&&<Card><Text style={s.muted}>LAST FILL · {new Date(lastFill.data[0].occurred_at).toLocaleDateString('en-NZ')}</Text><Text style={s.metric}>{lastFill.data[0].litres} L · ${lastFill.data[0].total_amount}</Text><Text>{lastFill.data[0].pump_price_per_litre??'—'}/L</Text></Card>}
      <Card><Text style={s.muted}>NEARBY LOWEST PRICE</Text>{nearby.data?.[0]?<><Text style={s.metric}>${nearby.data[0].price}/L · {nearby.data[0].fuel_type}</Text><Text>{nearby.data[0].distance_km} km · {freshness(nearby.data[0].observed_at)} · {nearby.data[0].verification_level}</Text></>:<Text>Enable location in Fuel to see nearby verified prices.</Text>}</Card>
    </Screen>
  );
}
