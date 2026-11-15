import React from 'react';
import {Text} from 'react-native';
import type {GameSource} from '../../product/dragonGameCorpusClient';
export default function DragonMediaImport(_props:{game:string;source:GameSource;onChanged:()=>void;disabled:boolean}){return <Text>Local media intake is available in the web cockpit; native can inspect and play sealed video.</Text>;}
