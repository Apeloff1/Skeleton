import React from 'react';
import { Redirect } from 'expo-router';

export default function IntakeRoute() {
  return <Redirect href={{ pathname: '/forge-operator', params: { tab: 'intake' } }} />;
}
