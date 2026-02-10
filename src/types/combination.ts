export interface Combination {
  input1: string; // tile ID
  input2: string; // tile ID
  output: string; // tile ID
}

export interface Recipe {
  tileId: string; // philosopher or writing tile ID
  requiredConcepts: string[]; // tile IDs that must all be unlocked
}
