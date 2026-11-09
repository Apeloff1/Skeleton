import React from 'react';
import { Redirect } from 'expo-router';

export default function ReportRoute() {
  return <Redirect href={{ pathname: '/forge-operator', params: { tab: 'report' } }} />;
}
