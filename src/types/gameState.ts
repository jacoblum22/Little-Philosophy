export interface CombinationAttempt {
  input1: string;
  input2: string;
  result: string | null;
  timestamp: number;
}

export interface GameState {
  unlockedTileIds: string[];
  combinationHistory: CombinationAttempt[];
}
