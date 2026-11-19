import type { Dispatch, SetStateAction } from 'react';
import { useAutosave } from '../../utils/useAutosave';

type Note = { id: string; text: string };

type AutosaveTuple = ReturnType<typeof useAutosave<Note[]>>;
type Setter = AutosaveTuple[1];
type Assert<T extends true> = T;
type AcceptsFunctionalUpdate = Assert<Setter extends Dispatch<SetStateAction<Note[]>> ? true : false>;

export type { AcceptsFunctionalUpdate };
