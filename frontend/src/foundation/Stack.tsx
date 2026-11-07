import React from 'react';
import { View, ViewProps, FlexAlignType } from 'react-native';
import { space, SpaceToken } from './tokens';

export interface StackProps extends ViewProps {
  gap?: SpaceToken | number;
  padding?: SpaceToken | number;
  direction?: 'row' | 'column';
  align?: FlexAlignType;
  justify?: 'flex-start' | 'center' | 'flex-end' | 'space-between' | 'space-around';
  wrap?: boolean;
}

/** Layout primitive: consistent spacing from tokens instead of ad-hoc margins. */
export function Stack({ gap = 'md', padding, direction = 'column', align, justify, wrap, style, ...rest }: StackProps) {
  return (
    <View
      style={[{
        flexDirection: direction,
        gap: space(gap),
        padding: padding === undefined ? undefined : space(padding),
        alignItems: align,
        justifyContent: justify,
        flexWrap: wrap ? 'wrap' : undefined,
      }, style]}
      {...rest}
    />
  );
}

export function Row(props: Omit<StackProps, 'direction'>) {
  return <Stack direction="row" align="center" {...props} />;
}

export default Stack;
