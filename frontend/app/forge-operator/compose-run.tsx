/** Deep link: /forge-operator/compose-run → compose tab. */
import React from 'react';
import { Redirect } from 'expo-router';

export default function ComposeRunRoute() {
  return <Redirect href={{ pathname: '/forge-operator', params: { tab: 'compose' } }} />;
}
