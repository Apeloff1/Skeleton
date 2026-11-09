import React from 'react';
import { Redirect } from 'expo-router';

export default function PlansRoute() {
  return <Redirect href={{ pathname: '/forge-operator', params: { tab: 'plans' } }} />;
}
