import React from 'react';
import { Redirect } from 'expo-router';

export default function CockpitRoute() {
  return <Redirect href={{ pathname: '/forge-operator', params: { tab: 'cockpit' } }} />;
}
