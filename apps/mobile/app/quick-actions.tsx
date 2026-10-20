import { useState } from "react";
import { Linking, Platform, Pressable, Text, View } from "react-native";
import { router } from "expo-router";
import { Card, Screen, s } from "../components/ui";
import { quickCaptureUrls } from "../lib/quick-capture-links";

export default function QuickActions() {
  const [error, setError] = useState<string>();
  async function openShortcuts() {
    if (Platform.OS !== "ios") return;
    try {
      await Linking.openURL("shortcuts://create-shortcut");
    } catch {
      setError("Open Apple's Shortcuts app manually to create a new shortcut.");
    }
  }
  return (
    <Screen title="Quick Capture shortcuts">
      <Card>
        <Text style={{fontSize:17,fontWeight:"700",color:"#153E32"}}>One tap. One photo. Done.</Text>
        <Text style={s.muted}>Create two shortcuts that open Autoroa's camera directly. No fuel forms or manual Save button.</Text>
        <Text style={{fontSize:16,fontWeight:"700",marginTop:8}}>1. Choose a capture action</Text>
        <Text style={{fontWeight:"600"}}>Receipt only (recommended)</Text>
        <Text selectable accessibilityLabel="Receipt Quick Capture link" style={{color:"#176D56",paddingVertical:8}}>
          {quickCaptureUrls.receipt}
        </Text>
        <Text style={{fontWeight:"600"}}>Receipt + odometer (optional)</Text>
        <Text selectable accessibilityLabel="Full Quick Capture link" style={{color:"#176D56",paddingVertical:8}}>
          {quickCaptureUrls.full}
        </Text>
        <Text style={{fontSize:16,fontWeight:"700",marginTop:10}}>2. Add an Apple Shortcut</Text>
        <Text>In Shortcuts, create a shortcut with the Open URLs action. Long-press and copy the link above into that action.</Text>
        <Text style={{fontSize:16,fontWeight:"700",marginTop:10}}>3. Put it where you need it</Text>
        <Text>Add the shortcut to your Home Screen, use Apple's Shortcuts widget, or assign it to your iPhone Action Button if supported.</Text>
        {Platform.OS === "ios" && <Pressable accessibilityRole="button" style={[s.button,{marginTop:10}]} onPress={() => void openShortcuts()}>
          <Text style={s.buttonText}>Create in Shortcuts</Text>
        </Pressable>}
        {error && <Text accessibilityRole="alert" style={s.danger}>{error}</Text>}
      </Card>
      <Card>
        <Text style={{fontWeight:"700",fontSize:16}}>What happens after your photo?</Text>
        <Text style={s.muted}>The photo is stored privately on this iPhone first. Upload and recognition resume when Autoroa is open and connected. You can check pending captures on Home.</Text>
        <Text style={s.muted}>Native Autoroa widgets and Siri App Intents will come with the validated Expo SDK upgrade. For now Apple's Shortcuts widgets provide one-tap entry.</Text>
      </Card>
      <Pressable onPress={() => router.back()}><Text style={s.link}>← Back</Text></Pressable>
    </Screen>
  );
}
