import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import * as Linking from "expo-linking";
import { AppState } from "react-native";
import { syncQuickCaptures } from "../lib/capture-queue";
import { router, Stack } from "expo-router";
import { useEffect, useState } from "react";
import { api, setAccessToken } from "../lib/api";
import { deleteStoredItem, getStoredItem, setStoredItem } from "../lib/storage";
import { supabase } from "../lib/supabase";
import {nextRoute} from '../lib/workflow';
export default function Root() {
  const [client] = useState(() => new QueryClient());
  useEffect(() => {
    async function routeSession(session: any) {
      await setAccessToken(session?.access_token ?? null);
      const priorUser=await getStoredItem('autoroa_user_id');const nextUser=session?.user?.id;
      if(priorUser&&priorUser!==nextUser)await deleteStoredItem(`autoroa_fillup_draft:${priorUser}`);
      if(nextUser)await setStoredItem('autoroa_user_id',nextUser);else if(priorUser)await deleteStoredItem(`autoroa_fillup_draft:${priorUser}`);
      if (!session) return router.replace(nextRoute({session:'signed-out',vehicleCount:0})!);
      void syncQuickCaptures();
      try {
        const vehicles = await api.get<Array<{id:string;is_primary:boolean}>>("/vehicles");
        const primary=vehicles.find(item=>item.is_primary)??vehicles[0];
        if(nextUser&&primary)await setStoredItem(`autoroa_primary_vehicle:${nextUser}`,primary.id);
        const initialUrl=await Linking.getInitialURL();
        const wantsCapture=initialUrl!=null&&Linking.parse(initialUrl).path?.split("/").filter(Boolean).join("/")==="quick-capture";
        if(wantsCapture&&vehicles.length>0)return;
        router.replace(nextRoute({session:'signed-in',vehicleCount:vehicles.length})! as any);
      } catch {
        const initialUrl=await Linking.getInitialURL();
        const wantsCapture=initialUrl!=null&&Linking.parse(initialUrl).path?.split("/").filter(Boolean).join("/")==="quick-capture";
        const cachedVehicle=nextUser?await getStoredItem(`autoroa_primary_vehicle:${nextUser}`):null;
        if(wantsCapture&&cachedVehicle)return;
        router.replace("/welcome");
      }
    }
    try {
      const client = supabase();
      client.auth.getSession().then(({ data }) => routeSession(data.session));
      const appState=AppState.addEventListener("change",state=>{if(state==="active")void syncQuickCaptures()});
      const { data } = client.auth.onAuthStateChange(async (_, session) => {
        await routeSession(session);
      });
      return () => {data.subscription.unsubscribe();appState.remove()};
    } catch {
      router.replace("/welcome");
    }
  }, []);
  return (
    <QueryClientProvider client={client}>
      <Stack screenOptions={{ headerShown: false }}>
        <Stack.Screen name="welcome" />
        <Stack.Screen name="onboarding/vehicle" />
        <Stack.Screen name="(tabs)" />
        <Stack.Screen name="fill-up" options={{ presentation: "modal" }} />
        <Stack.Screen name="quick-capture" options={{ presentation: "fullScreenModal" }} />
        <Stack.Screen name="capture-review/[id]" />
        <Stack.Screen name="fill-up/[id]" />
        <Stack.Screen name="vehicle/[id]" />
      </Stack>
    </QueryClientProvider>
  );
}
