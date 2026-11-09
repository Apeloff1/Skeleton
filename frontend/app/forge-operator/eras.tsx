import React from 'react';
import { Redirect } from 'expo-router';

export default function ErasRoute() {
  return <Redirect href={{ pathname: '/forge-operator', params: { tab: 'eras' } }} />;
}
