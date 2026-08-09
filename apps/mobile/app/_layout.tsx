import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
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
      const priorUser=await getStoredItem('carfolio_user_id');const nextUser=session?.user?.id;
      if(priorUser&&priorUser!==nextUser)await deleteStoredItem(`carfolio_fillup_draft:${priorUser}`);
      if(nextUser)await setStoredItem('carfolio_user_id',nextUser);else if(priorUser)await deleteStoredItem(`carfolio_fillup_draft:${priorUser}`);
      if (!session) return router.replace(nextRoute({session:'signed-out',vehicleCount:0})!);
      try {
        const vehicles = await api.get<unknown[]>("/vehicles");
        router.replace(nextRoute({session:'signed-in',vehicleCount:vehicles.length})! as any);
      } catch {
        router.replace("/welcome");
      }
    }
    try {
      const client = supabase();
      client.auth.getSession().then(({ data }) => routeSession(data.session));
      const { data } = client.auth.onAuthStateChange(async (_, session) => {
        await routeSession(session);
      });
      return () => data.subscription.unsubscribe();
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
        <Stack.Screen name="fill-up/[id]" />
        <Stack.Screen name="vehicle/[id]" />
      </Stack>
    </QueryClientProvider>
  );
}
