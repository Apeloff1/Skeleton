import React from 'react';
import { Redirect } from 'expo-router';

export default function WalkRoute() {
  return <Redirect href={{ pathname: '/forge-operator', params: { tab: 'walk' } }} />;
}
