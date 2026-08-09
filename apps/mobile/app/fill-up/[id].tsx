import {useEffect,useState} from 'react';
import {Pressable,Switch,Text,View} from 'react-native';
import {router,useLocalSearchParams} from 'expo-router';
import {useQuery,useQueryClient} from '@tanstack/react-query';
import type {FillUp} from '../../../../packages/types/src';
import {Button,Card,FormField,Screen,s} from '../../components/ui';
import {api} from '../../lib/api';
import {fillEditSchema,fuels} from '../../lib/car-validation';
import {acknowledgeEditFillUpWarning,classifyEditFillUpWarning,editFillUpWarningMessage,emptyEditFillUpAcknowledgements,invalidateEditedFillUpQueries,patchEditedFillUp,type EditFillUpAcknowledgements,type EditFillUpWarning} from '../../lib/workflow';

export default function EditFillUp(){
  const {id}=useLocalSearchParams<{id:string}>();const cache=useQueryClient();
  const detail=useQuery({queryKey:['fillup',id],queryFn:()=>api.get<FillUp>(`/fill-ups/${id}`),enabled:!!id});
  const [edit,setEdit]=useState<any>();const [error,setError]=useState('');const [warning,setWarning]=useState<EditFillUpWarning>();const [ack,setAck]=useState<EditFillUpAcknowledgements>(emptyEditFillUpAcknowledgements);const [stationSearch,setStationSearch]=useState('');const [stationResults,setStationResults]=useState<any[]>([]);const [deleting,setDeleting]=useState(false);const [saving,setSaving]=useState(false);
  useEffect(()=>{if(detail.data)setEdit({...detail.data})},[detail.data]);
  async function save(acknowledgements:EditFillUpAcknowledgements){const parsed=fillEditSchema.safeParse(edit);if(!parsed.success){setError(parsed.error.issues[0]?.message??'Check the editable fields.');return}try{setSaving(true);setError('');await patchEditedFillUp(api.patch,id,parsed.data,acknowledgements);await invalidateEditedFillUpQueries(options=>cache.invalidateQueries(options));router.back()}catch(caught){const next=classifyEditFillUpWarning(caught);if(next){setWarning(next);return}setError(caught instanceof Error?caught.message:'Fill-up could not be saved.')}finally{setSaving(false)}}
  async function remove(){try{setError('');await api.delete(`/fill-ups/${id}`);await invalidateEditedFillUpQueries(options=>cache.invalidateQueries(options));await cache.removeQueries({queryKey:['fillup',id]});router.back()}catch(caught){setDeleting(false);setError(caught instanceof Error?caught.message:'Fill-up could not be deleted.')}}
  return <Screen title="Edit fill-up">
    <Pressable accessibilityRole="link" onPress={()=>router.back()}><Text style={s.link}>← Back to My Car</Text></Pressable>
    {detail.isLoading&&<Text>Loading fill-up…</Text>}{detail.isError&&<Text accessibilityRole="alert">Fill-up could not be loaded.</Text>}
    {edit&&<Card><Text style={s.muted}>Fields with an outlined box can be edited. Calculated economy values update automatically after saving.</Text>
      <FormField label="Station search" placeholder="Search station, city, or address" value={stationSearch} onChangeText={setStationSearch} onSubmitEditing={async()=>setStationResults(await api.get<any[]>(`/fuel-stations/search?q=${encodeURIComponent(stationSearch)}`))}/>
      {stationResults.map(station=><Pressable style={[s.choice,edit.station_id===station.id&&s.choiceSelected]} key={station.id} onPress={()=>setEdit((current:any)=>({...current,station_id:station.id}))}><Text>{station.name} · {station.address_line}{edit.station_id===station.id?' ✓':''}</Text></Pressable>)}
      <Pressable style={s.choice} onPress={()=>setEdit((current:any)=>({...current,station_id:null}))}><Text>Clear station selection</Text></Pressable>
      {[['occurred_at','Date and time (ISO)'],['litres','Litres'],['pump_price_per_litre','Pump price per litre'],['discount_amount','Discount amount'],['total_amount','Total amount'],['odometer_km','Odometer (km)'],['notes','Notes']].map(([key,label])=><FormField key={key} label={label} value={String(edit[key]??'')} onChangeText={value=>setEdit((current:any)=>({...current,[key]:value}))}/>)}
      <Text style={s.fieldLabel}>Fuel type</Text><View style={{flexDirection:'row',flexWrap:'wrap',gap:8}}>{fuels.map(fuel=><Pressable accessibilityRole="radio" accessibilityState={{selected:edit.fuel_type===fuel}} style={[s.choice,edit.fuel_type===fuel&&s.choiceSelected]} key={fuel} onPress={()=>setEdit((current:any)=>({...current,fuel_type:fuel}))}><Text>{fuel}{edit.fuel_type===fuel?' ✓':''}</Text></Pressable>)}</View>
      <View style={{flexDirection:'row',justifyContent:'space-between',alignItems:'center'}}><Text style={s.fieldLabel}>Full tank</Text><Switch accessibilityLabel="Full tank" value={!!edit.full_tank} onValueChange={value=>setEdit((current:any)=>({...current,full_tank:value}))}/></View>
      <View style={{flexDirection:'row',justifyContent:'space-between',alignItems:'center'}}><Text style={s.fieldLabel}>Missed previous fill</Text><Switch accessibilityLabel="Missed previous fill" value={!!edit.missed_previous_fill} onValueChange={value=>setEdit((current:any)=>({...current,missed_previous_fill:value}))}/></View>
      {warning&&<View><Text accessibilityRole="alert">{editFillUpWarningMessage(warning)}</Text><Button label="Confirm and save" onPress={()=>{const next=acknowledgeEditFillUpWarning(ack,warning);setAck(next);setWarning(undefined);void save(next)}}/></View>}
      {error&&<Text accessibilityRole="alert">{error}</Text>}<Button label={saving?'Saving…':'Save fill-up'} disabled={saving} onPress={()=>void save(ack)}/><Pressable accessibilityRole="button" onPress={()=>router.back()}><Text style={s.link}>Cancel</Text></Pressable>
    </Card>}
    {edit&&<Card><Text style={s.danger}>Delete fill-up</Text><Text style={s.muted}>Deleting changes the intervals around this entry. Fuel economy will be recalculated from the remaining history.</Text>{deleting?<><Text>Delete this fill-up permanently?</Text><Button label="Yes, delete fill-up" onPress={()=>void remove()}/><Pressable accessibilityRole="button" onPress={()=>setDeleting(false)}><Text style={s.link}>Keep fill-up</Text></Pressable></>:<Pressable accessibilityRole="button" onPress={()=>setDeleting(true)}><Text style={s.danger}>Delete fill-up…</Text></Pressable>}</Card>}
  </Screen>
}
