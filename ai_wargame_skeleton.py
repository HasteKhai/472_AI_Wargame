from __future__ import annotations
import argparse
import copy
from datetime import datetime
from enum import Enum
from dataclasses import dataclass, field
from time import sleep
from typing import Tuple, TypeVar, Type, Iterable, ClassVar
import random
import requests
import time

# maximum and minimum values for our heuristic scores (usually represents an end of game condition)
MAX_HEURISTIC_SCORE = 2000000000
MIN_HEURISTIC_SCORE = -2000000000


class UnitType(Enum):
    """Every unit type."""
    AI = 0
    Tech = 1
    Virus = 2
    Program = 3
    Firewall = 4


class Player(Enum):
    """The 2 players."""
    Attacker = 0
    Defender = 1

    def next(self) -> Player:
        """The next (other) player."""
        if self is Player.Attacker:
            return Player.Defender
        else:
            return Player.Attacker


class GameType(Enum):
    AttackerVsDefender = 0
    AttackerVsComp = 1
    CompVsDefender = 2
    CompVsComp = 3


##############################################################################################################

@dataclass(slots=True)
class Unit:
    player: Player = Player.Attacker
    type: UnitType = UnitType.Program
    health: int = 9
    # class variable: damage table for units (based on the unit type constants in order)
    damage_table: ClassVar[list[list[int]]] = [
        [3, 3, 3, 3, 1],  # AI
        [1, 1, 6, 1, 1],  # Tech
        [9, 6, 1, 6, 1],  # Virus
        [3, 3, 3, 3, 1],  # Program
        [1, 1, 1, 1, 1],  # Firewall
    ]
    # class variable: repair table for units (based on the unit type constants in order)
    repair_table: ClassVar[list[list[int]]] = [
        [0, 1, 1, 0, 0],  # AI
        [3, 0, 0, 3, 3],  # Tech
        [0, 0, 0, 0, 0],  # Virus
        [0, 0, 0, 0, 0],  # Program
        [0, 0, 0, 0, 0],  # Firewall
    ]

    def is_alive(self) -> bool:
        """Are we alive ?"""
        return self.health > 0

    def mod_health(self, health_delta: int):
        """Modify this unit's health by delta amount."""
        self.health += health_delta
        if self.health < 0:
            self.health = 0
        elif self.health > 9:
            self.health = 9

    def to_string(self) -> str:
        """Text representation of this unit."""
        p = self.player.name.lower()[0]
        t = self.type.name.upper()[0]
        return f"{p}{t}{self.health}"

    def __str__(self) -> str:
        """Text representation of this unit."""
        return self.to_string()

    def damage_amount(self, target: Unit) -> int:
        """How much can this unit damage another unit."""
        amount = self.damage_table[self.type.value][target.type.value]
        if target.health - amount < 0:
            return target.health
        return amount

    def repair_amount(self, target: Unit) -> int:
        """How much can this unit repair another unit."""
        amount = self.repair_table[self.type.value][target.type.value]
        if target.health + amount > 9:
            return 9 - target.health
        return amount


##############################################################################################################

@dataclass(slots=True)
class Coord:
    """Representation of a game cell coordinate (row, col)."""
    row: int = 0
    col: int = 0

    def col_string(self) -> str:
        """Text representation of this Coord's column."""
        coord_char = '?'
        if self.col < 16:
            coord_char = "0123456789abcdef"[self.col]
        return str(coord_char)

    def row_string(self) -> str:
        """Text representation of this Coord's row."""
        coord_char = '?'
        if self.row < 26:
            coord_char = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"[self.row]
        return str(coord_char)

    def to_string(self) -> str:
        """Text representation of this Coord."""
        return self.row_string() + self.col_string()

    def __str__(self) -> str:
        """Text representation of this Coord."""
        return self.to_string()

    def clone(self) -> Coord:
        """Clone a Coord."""
        return copy.copy(self)

    def iter_range(self, dist: int) -> Iterable[Coord]:
        """Iterates over Coords inside a rectangle centered on our Coord."""
        for row in range(self.row - dist, self.row + 1 + dist):
            for col in range(self.col - dist, self.col + 1 + dist):
                yield Coord(row, col)

    def iter_adjacent(self) -> Iterable[Coord]:
        """Iterates over adjacent Coords."""
        yield Coord(self.row - 1, self.col)
        yield Coord(self.row, self.col - 1)
        yield Coord(self.row + 1, self.col)
        yield Coord(self.row, self.col + 1)

    @classmethod
    def from_string(cls, s: str) -> Coord | None:
        """Create a Coord from a string. ex: D2."""
        s = s.strip()
        for sep in " ,.:;-_":
            s = s.replace(sep, "")
        if (len(s) == 2):
            coord = Coord()
            coord.row = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".find(s[0:1].upper())
            coord.col = "0123456789abcdef".find(s[1:2].lower())
            return coord
        else:
            return None


##############################################################################################################

@dataclass(slots=True)
class CoordPair:
    """Representation of a game move or a rectangular area via 2 Coords."""
    src: Coord = field(default_factory=Coord)
    dst: Coord = field(default_factory=Coord)

    def to_string(self) -> str:
        """Text representation of a CoordPair."""
        return self.src.to_string() + " " + self.dst.to_string()

    def __str__(self) -> str:
        """Text representation of a CoordPair."""
        return self.to_string()

    def clone(self) -> CoordPair:
        """Clones a CoordPair."""
        return copy.copy(self)

    def iter_rectangle(self) -> Iterable[Coord]:
        """Iterates over cells of a rectangular area."""
        for row in range(self.src.row, self.dst.row + 1):
            for col in range(self.src.col, self.dst.col + 1):
                yield Coord(row, col)

    @classmethod
    def from_quad(cls, row0: int, col0: int, row1: int, col1: int) -> CoordPair:
        """Create a CoordPair from 4 integers."""
        return CoordPair(Coord(row0, col0), Coord(row1, col1))

    @classmethod
    def from_dim(cls, dim: int) -> CoordPair:
        """Create a CoordPair based on a dim-sized rectangle."""
        return CoordPair(Coord(0, 0), Coord(dim - 1, dim - 1))

    @classmethod
    def from_string(cls, s: str) -> CoordPair | None:
        """Create a CoordPair from a string. ex: A3 B2"""
        s = s.strip()
        for sep in " ,.:;-_":
            s = s.replace(sep, "")
        if (len(s) == 4):
            coords = CoordPair()
            coords.src.row = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".find(s[0:1].upper())
            coords.src.col = "0123456789abcdef".find(s[1:2].lower())
            coords.dst.row = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".find(s[2:3].upper())
            coords.dst.col = "0123456789abcdef".find(s[3:4].lower())
            return coords
        else:
            return None


##############################################################################################################

@dataclass(slots=True)
class Options:
    """Representation of the game options."""
    dim: int = 5
    max_depth: int | None = 15
    min_depth: int | None = 2
    max_time: float | None = 5
    game_type: GameType = GameType.AttackerVsDefender
    alpha_beta: bool = True
    max_turns: int | None = 10
    randomize_moves: bool = True
    broker: str | None = None
    heuristic: str | None = 'e2'


##############################################################################################################

@dataclass(slots=True)
class Stats:
    """Representation of the global game statistics."""
    evaluations_per_depth: dict[int, int] = field(default_factory=dict)
    total_seconds: float = 0.0

    # Added *****************
    heuristic_score: float = 0.0
    cumulative_evals: int = 0


##############################################################################################################

@dataclass(slots=True)
class Game:
    """Representation of the game state."""
    board: list[list[Unit | None]] = field(default_factory=list)
    next_player: Player = Player.Attacker
    turns_played: int = 0
    options: Options = field(default_factory=Options)
    stats: Stats = field(default_factory=Stats)
    _attacker_has_ai: bool = True
    _defender_has_ai: bool = True

    def __post_init__(self):
        """Automatically called after class init to set up the default board state."""
        dim = self.options.dim
        self.board = [[None for _ in range(dim)] for _ in range(dim)]
        md = dim - 1
        self.set(Coord(0, 0), Unit(player=Player.Defender, type=UnitType.AI))
        self.set(Coord(1, 0), Unit(player=Player.Defender, type=UnitType.Tech))
        self.set(Coord(0, 1), Unit(player=Player.Defender, type=UnitType.Tech))
        self.set(Coord(2, 0), Unit(player=Player.Defender, type=UnitType.Firewall))
        self.set(Coord(0, 2), Unit(player=Player.Defender, type=UnitType.Firewall))
        self.set(Coord(1, 1), Unit(player=Player.Defender, type=UnitType.Program))
        self.set(Coord(md, md), Unit(player=Player.Attacker, type=UnitType.AI))
        self.set(Coord(md - 1, md), Unit(player=Player.Attacker, type=UnitType.Virus))
        self.set(Coord(md, md - 1), Unit(player=Player.Attacker, type=UnitType.Virus))
        self.set(Coord(md - 2, md), Unit(player=Player.Attacker, type=UnitType.Program))
        self.set(Coord(md, md - 2), Unit(player=Player.Attacker, type=UnitType.Program))
        self.set(Coord(md - 1, md - 1), Unit(player=Player.Attacker, type=UnitType.Firewall))

    def clone(self) -> Game:
        """Make a new copy of a game for minimax recursion.

        Shallow copy of everything except the board (options and stats are shared).
        """
        new = copy.copy(self)
        new.board = copy.deepcopy(self.board)
        return new

    def is_empty(self, coord: Coord) -> bool:
        """Check if contents of a board cell of the game at Coord is empty (must be valid coord)."""
        return self.board[coord.row][coord.col] is None

    def get(self, coord: Coord) -> Unit | None:
        """Get contents of a board cell of the game at Coord."""
        if self.is_valid_coord(coord):
            return self.board[coord.row][coord.col]
        else:
            return None

    def set(self, coord: Coord, unit: Unit | None):
        """Set contents of a board cell of the game at Coord."""
        if self.is_valid_coord(coord):
            self.board[coord.row][coord.col] = unit

    def remove_dead(self, coord: Coord):
        """Remove unit at Coord if dead."""
        unit = self.get(coord)
        if unit is not None and not unit.is_alive():
            self.set(coord, None)
            if unit.type == UnitType.AI:
                if unit.player == Player.Attacker:
                    self._attacker_has_ai = False
                else:
                    self._defender_has_ai = False

    def mod_health(self, coord: Coord, health_delta: int):
        """Modify health of unit at Coord (positive or negative delta)."""
        target = self.get(coord)
        if target is not None:
            target.mod_health(health_delta)
            self.remove_dead(coord)

        # ---------------------------------------Added Methods---------------------------------------------------#

    def create_File(self):
        alpha_beta_str = "true" if self.options.alpha_beta else "false"
        trace_filename = f"gameTrace-{alpha_beta_str}-{int(self.options.max_time)}-{self.options.max_turns}.txt"

        with open(trace_filename, "w") as trace_file:
            trace_file.write("Game Parameters:\n")
            trace_file.write(f"Value of the timeout: {self.options.max_time} seconds\n")
            trace_file.write(f"Max number of turns: {self.options.max_turns}\n")
            trace_file.write(f"Alpha-Beta: {self.options.alpha_beta}\n")

            if self.options.game_type == GameType.AttackerVsComp:
                trace_file.write(f"Player 1: {self.next_player.name}\n")
                trace_file.write(
                    f"Player 2: {self.next_player.next().name} is an AI. Heuristic: {self.options.heuristic}\n")
            elif self.options.game_type == GameType.CompVsDefender:
                trace_file.write(f"Player 1: {self.next_player.name} is an AI. Heuristic: {self.options.heuristic}\n")
                trace_file.write(f"Player 2: {self.next_player.next().name}\n")
            elif self.options.game_type == GameType.CompVsComp:
                trace_file.write(f"Player 1: {self.next_player.name} is an AI. Heuristic: {self.options.heuristic}\n")
                trace_file.write(
                    f"Player 2: {self.next_player.next().name} is an AI. Heuristic: {self.options.heuristic}\n")
            else:
                trace_file.write(f"Player 1: {self.next_player.name}\n")
                trace_file.write(f"Player 2: {self.next_player.next().name}\n")

            dim = self.options.dim
            coord = Coord()
            trace_file.write("\nInitial Configuration Of The Board:\n")
            trace_file.write("\n   ")
            for col in range(dim):
                coord.col = col
                label = coord.col_string()
                trace_file.write(f"{label:^3} ")
            trace_file.write("\n")
            for row in range(dim):
                coord.row = row
                label = coord.row_string()
                trace_file.write(f"{label}: ")
                for col in range(dim):
                    coord.col = col
                    unit = self.get(coord)
                    if unit is None:
                        trace_file.write(" .  ")
                    else:
                        trace_file.write(f"{str(unit):^3} ")

                trace_file.write("\n")

    def update_Current_Board(self, move, src, dst) -> str:

        alpha_beta_str = "true" if self.options.alpha_beta else "false"
        trace_filename = f"gameTrace-{alpha_beta_str}-{int(self.options.max_time)}-{self.options.max_turns}.txt"

        with open(trace_filename, "a") as trace_file:
            trace_file.write("\n==========================================\n")
            trace_file.write(f"\nTurn #{self.turns_played + 1}\n")
            trace_file.write(f"Name of Player: {self.next_player.name}\n")

            if move == 'Self-Destruct':
                trace_file.write(f"Action taken: {move} at {src}\n")
            else:
                trace_file.write(f"Action taken: {move} from {src} to {dst}\n")

            if self.options.game_type == GameType.AttackerVsComp:
                if self.next_player == Player.Defender:
                    trace_file.write(f"Time for this action: {self.stats.total_seconds}\n")
                    self.stats.total_seconds = 0
                    trace_file.write(f"Cumulative evals: {self.stats.cumulative_evals}M\n")


            elif self.options.game_type == GameType.CompVsDefender:
                if self.next_player == Player.Defender:
                    if self.next_player == Player.Defender:
                        trace_file.write(f"Time for this action: {self.stats.total_seconds}\n")
                        self.stats.total_seconds = 0
                        trace_file.write(f"Heuristic score: {self.stats.heuristic_score}\n")
                        trace_file.write(f"Cumulative evals: {self.stats.cumulative_evals}M\n")


            elif self.options.game_type == GameType.CompVsComp:
                trace_file.write(f"Time for this action: {self.stats.total_seconds}\n")
                self.stats.total_seconds = 0
                trace_file.write(f"Heuristic score: {self.stats.heuristic_score}\n")
                trace_file.write(f"Cumulative evals: {self.stats.cumulative_evals}M\n")

            dim = self.options.dim
            output = ""
            coord = Coord()
            trace_file.write("\nNew Configuration Of The Board:\n")
            trace_file.write("\n   ")
            output += "\n   "
            for col in range(dim):
                coord.col = col
                label = coord.col_string()
                trace_file.write(f"{label:^3} ")
                output += f"{label:^3} "
            trace_file.write("\n")
            output += "\n"
            for row in range(dim):
                coord.row = row
                label = coord.row_string()
                trace_file.write(f"{label}: ")
                output += f"{label}: "
                for col in range(dim):
                    coord.col = col
                    unit = self.get(coord)
                    if unit is None:
                        trace_file.write(" .  ")
                        output += " .  "
                    else:
                        trace_file.write(f"{str(unit):^3} ")
                        output += f"{str(unit):^3} "

                trace_file.write("\n")
                output += "\n"

            if self.has_winner():
                trace_file.write(f"\n{self.has_winner().name} wins in {self.turns_played + 1} turns\n")

            return output

    def move_direction(self, coords: CoordPair) -> str:
        src = coords.src
        dst = coords.dst

        if coords.src.row != coords.dst.row and coords.src.col != coords.dst.col:
            return 'illegal'

        if abs(coords.dst.row - coords.src.row) > 1:
            return 'illegal'

        if abs(coords.dst.col - coords.src.col) > 1:
            return 'illegal'

        if coords.src.row > coords.dst.row:

            return 'up'
        elif coords.src.row < coords.dst.row:

            return 'down'
        elif coords.src.col > coords.dst.col:

            return 'left'
        elif coords.src.col < coords.dst.col:

            return 'right'
        else:
            return 'illegal'

    def check_IsCombatState(self, coords: CoordPair) -> bool:
        for adjacents in coords.src.iter_adjacent():
            unit = self.get(adjacents)
            # CHANGE
            if unit is not None and unit.player != self.next_player:
                return True
        return False

    def verify_UnitConstraints(self, coords: CoordPair) -> bool:
        if self.move_direction(coords) == 'illegal':
            return False

        unit = self.get(coords.src)

        if unit.type is UnitType.AI or unit.type is UnitType.Firewall or unit.type is UnitType.Program:
            if self.check_IsCombatState(coords):
                return False

            if unit.player == Player.Attacker:

                if self.move_direction(coords) == 'down' or self.move_direction(coords) == 'right':
                    return False
            else:

                if self.move_direction(coords) == 'up' or self.move_direction(coords) == 'left':
                    return False

        return True

    def can_Repair(self, coords: CoordPair) -> bool:
        unit = self.get(coords.src)
        unit_to_heal = self.get(coords.dst)

        # Unit can't heal themselves or empty non-existant units
        # Unit can't heal if their repair amount is 0
        if unit_to_heal is None or unit.repair_amount(unit_to_heal) == 0 or unit_to_heal is not unit :
            return False

        # Check if the unit to heal is adjacent
        if not abs(coords.src.row - coords.dst.row) + abs(
                coords.src.col - coords.dst.col) == 1 and unit_to_heal.player != self.next_player:
            return False

        # Units can heal another unit that is already at full health
        if unit_to_heal.health == 9:
            return False

        # Techs can't heal Viruses
        if unit.type == UnitType.Tech:
            if unit_to_heal.type == UnitType.Virus:
                return False

        return True

    def move_Type(self, coords: CoordPair) -> str:

        # Is it an attack?
        destination = self.get(coords.dst)

        if not destination is None and destination.player != self.next_player:
            return 'Attack'

        # Is it a self-destruct?
        if coords.dst == coords.src:
            return 'Self-Destruct'

        # Is it a repair?
        if not destination is None and destination.player == self.next_player:

            return 'Repair'


        # If all the above doesn't match, then it is a move
        else:

            return 'Move'

    # ------------------------------------------------------------------------------------------#
    def is_valid_move(self, coords: CoordPair) -> bool:
        """Validate a move expressed as a CoordPair. TODO: WRITE MISSING CODE!!!"""

        # Validate the Coordinates
        if not self.is_valid_coord(coords.src) or not self.is_valid_coord(coords.dst):
            return False

        unit = self.get(coords.src)

        if unit is None or unit.player != self.next_player:
            return False

        move = self.move_Type(coords)

        # Determine the move type
        if move == 'Attack':
            if self.check_IsCombatState(coords):

                return True
            else:
                return False
        if move == 'Self-Destruct':
            return True

        if move == 'Repair':
            if self.can_Repair(coords):

                return True
            else:
                return False

        unit = self.get(coords.dst)

        if move == 'Move':

            if not unit is None:
                return False
            if not self.verify_UnitConstraints(coords):
                return False

        return (unit is None)

    def perform_move(self, coords: CoordPair) -> Tuple[bool, str]:
        """Validate and perform a move expressed as a CoordPair. TODO: WRITE MISSING CODE!!!"""
        player_unit = self.get(coords.src)

        if self.is_valid_move(coords):

            move = self.move_Type(coords)

            if move == 'Move':
                self.set(coords.dst, self.get(coords.src))
                self.set(coords.src, None)
                self.update_Current_Board(move, coords.src, coords.dst)
                return (True, "")

            if move == 'Attack' and self.check_IsCombatState(coords):

                adversary_unit = self.get(coords.dst)

                self.mod_health(coords.src, -adversary_unit.damage_amount(player_unit))
                self.mod_health(coords.dst, -player_unit.damage_amount(adversary_unit))

                if not player_unit.is_alive():
                    self.remove_dead(coords.src)

                if not adversary_unit.is_alive():
                    self.remove_dead(coords.dst)

                self.update_Current_Board(move, coords.src, coords.dst)
                return (True, "Damage Dealt")

            if move == 'Self-Destruct':
                self.mod_health(coords.src, -player_unit.health)
                for surrounding in coords.src.iter_range(1):
                    unit = self.get(surrounding)
                    if unit is not None:
                        self.mod_health(surrounding, -2)
                        if unit.health == 0:
                            self.remove_dead(surrounding)

                self.remove_dead(coords.src)
                self.update_Current_Board(move, coords.src, coords.dst)
                return (True, "Unit has self-destructed")

            if move == 'Repair' and self.can_Repair(coords):
                unit_to_heal = self.get(coords.dst)

                self.mod_health(coords.dst, player_unit.repair_amount(unit_to_heal))
                self.update_Current_Board(move, coords.src, coords.dst)
                return (True, "Restored Health")

        if self.options.game_type == GameType.AttackerVsComp:
            if (self.next_player == Player.Defender):
                self._defender_has_ai = False
        if self.options.game_type == GameType.CompVsDefender:
            if (self.next_player == Player.Defender):
                self._defender_has_ai = False
        if self.options.game_type == GameType.CompVsComp:
            self._defender_has_ai = False

        return (False, "Invalid move")

    def next_turn(self):
        """Transitions game to the next turn."""
        self.next_player = self.next_player.next()
        self.turns_played += 1

    def to_string(self) -> str:
        """Pretty text representation of the game."""
        dim = self.options.dim
        output = ""
        output += f"Next player: {self.next_player.name}\n"
        output += f"Turns played: {self.turns_played}\n"
        coord = Coord()
        output += "\n   "
        for col in range(dim):
            coord.col = col
            label = coord.col_string()
            output += f"{label:^3} "
        output += "\n"
        for row in range(dim):
            coord.row = row
            label = coord.row_string()
            output += f"{label}: "
            for col in range(dim):
                coord.col = col
                unit = self.get(coord)
                if unit is None:
                    output += " .  "
                else:
                    output += f"{str(unit):^3} "
            output += "\n"
        return output

    def __str__(self) -> str:
        """Default string representation of a game."""
        return self.to_string()

    def is_valid_coord(self, coord: Coord) -> bool:
        """Check if a Coord is valid within out board dimensions."""
        dim = self.options.dim
        if coord.row < 0 or coord.row >= dim or coord.col < 0 or coord.col >= dim:
            return False
        return True

    def read_move(self) -> CoordPair:
        """Read a move from keyboard and return as a CoordPair."""
        while True:
            s = input(F'Player {self.next_player.name}, enter your move: ')
            coords = CoordPair.from_string(s)
            if coords is not None and self.is_valid_coord(coords.src) and self.is_valid_coord(coords.dst):
                return coords
            else:
                print('Invalid coordinates! Try again.')

    def human_turn(self):
        """Human player plays a move (or get via broker)."""
        if self.options.broker is not None:
            print("Getting next move with auto-retry from game broker...")
            while True:
                mv = self.get_move_from_broker()
                if mv is not None:
                    (success, result) = self.perform_move(mv)
                    print(f"Broker {self.next_player.name}: ", end='')
                    print(result)
                    if success:
                        self.next_turn()
                        break
                sleep(0.1)
        else:
            while True:
                mv = self.read_move()
                (success, result) = self.perform_move(mv)
                if success:
                    print(f"Player {self.next_player.name}: ", end='')
                    print(result)
                    self.next_turn()
                    break
                else:
                    print("The move is not valid! Try again.")

    def computer_turn(self) -> CoordPair | None:
        """Computer plays a move."""
        mv = self.suggest_move()
        if mv is not None:
            (success, result) = self.perform_move(mv)
            if success:
                print(f"Computer {self.next_player.name}: ", end='')
                print(result)
                self.next_turn()
        return mv

    def player_units(self, player: Player) -> Iterable[Tuple[Coord, Unit]]:
        """Iterates over all units belonging to a player."""
        for coord in CoordPair.from_dim(self.options.dim).iter_rectangle():
            unit = self.get(coord)
            if unit is not None and unit.player == player:
                yield (coord, unit)

    def is_finished(self) -> bool:
        """Check if the game is over."""
        return self.has_winner() is not None

    def has_winner(self) -> Player | None:
        """Check if the game is over and returns winner"""
        if self.options.max_turns is not None and self.turns_played >= self.options.max_turns:
            return Player.Defender
        if self._attacker_has_ai:
            if self._defender_has_ai:
                return None
            else:
                return Player.Attacker
        return Player.Defender

    def move_candidates(self) -> Iterable[CoordPair]:
        """Generate valid move candidates for the next player."""
        move = CoordPair()
        for (src, _) in self.player_units(self.next_player):
            move.src = src
            for dst in src.iter_adjacent():
                move.dst = dst
                if self.is_valid_move(move):
                    yield move.clone()
            move.dst = src
            yield move.clone()

    def random_move(self) -> Tuple[int, CoordPair | None, float]:
        """Returns a random move."""
        move_candidates = list(self.move_candidates())
        random.shuffle(move_candidates)
        if len(move_candidates) > 0:
            return (0, move_candidates[0], 1)
        else:
            return (0, None, 0)

    # ---------------------------------------Heuristics, Alpha-Beta, and Minimax-------------------------------------------#
    def heuristic_0(self, game) -> int:

        VP1 = 0
        TP1 = 0
        FP1 = 0
        PP1 = 0
        AIP1 = 0

        VP2 = 0
        TP2 = 0
        FP2 = 0
        PP2 = 0
        AIP2 = 0

        unitsP1 = [unit for _, unit in game.player_units(Player.Attacker)]
        unitsP2 = [unit for _, unit in game.player_units(Player.Defender)]

        for unit in unitsP1:
            if unit.type == UnitType.Virus:
                VP1 += 1
            elif unit.type == UnitType.Tech:
                TP1 += 1
            elif unit.type == UnitType.Tech:
                FP1 += 1
            elif unit.type == UnitType.Tech:
                PP1 += 1
            elif unit.type == UnitType.Tech:
                AIP1 += 1

        for unit in unitsP2:
            if unit.type == UnitType.Virus:
                VP2 += 1
            elif unit.type == UnitType.Tech:
                TP2 += 1
            elif unit.type == UnitType.Tech:
                FP2 += 1
            elif unit.type == UnitType.Tech:
                PP2 += 1
            elif unit.type == UnitType.Tech:
                AIP2 += 1

        return (3 * VP1 + 3 * TP1 + 3 * FP1 + 9999 * AIP1) - (3 * VP2 + 3 * TP2 + 3 * FP2 + 9999 * AIP2)

    def heuristic_1(self, game) -> int:

        unitsP1_Healths = [unit for _, unit in game.player_units(Player.Attacker)]
        unitsP2_Healths = [unit for _, unit in game.player_units(Player.Defender)]

        totalHealthP1 = 0
        totalHealthP2 = 0

        for unit in unitsP1_Healths:
            totalHealthP1 += unit.health

        for unit in unitsP2_Healths:
            totalHealthP2 += unit.health

        return (totalHealthP1) - (totalHealthP2)

    def heuristic_2(self, game) -> int:
        VP1 = 0
        TP1 = 0
        FP1 = 0
        PP1 = 0
        AIP1 = 0

        VP2 = 0
        TP2 = 0
        FP2 = 0
        PP2 = 0
        AIP2 = 0

        unitsP1 = [unit for _, unit in game.player_units(Player.Attacker)]
        unitsP2 = [unit for _, unit in game.player_units(Player.Defender)]

        for unit in unitsP1:
            if unit.type == UnitType.Virus:
                VP1 += 1
            elif unit.type == UnitType.Tech:
                TP1 += 1
            elif unit.type == UnitType.Tech:
                FP1 += 1
            elif unit.type == UnitType.Tech:
                PP1 += 1
            elif unit.type == UnitType.Tech:
                AIP1 += 1

        for unit in unitsP2:
            if unit.type == UnitType.Virus:
                VP2 += 1
            elif unit.type == UnitType.Tech:
                TP2 += 1
            elif unit.type == UnitType.Tech:
                FP2 += 1
            elif unit.type == UnitType.Tech:
                PP2 += 1
            elif unit.type == UnitType.Tech:
                AIP2 += 1

        unitsP1_Healths = [unit for _, unit in game.player_units(Player.Attacker)]
        unitsP2_Healths = [unit for _, unit in game.player_units(Player.Defender)]

        totalHealthP1 = 0
        totalHealthP2 = 0

        for unit in unitsP1_Healths:
            totalHealthP1 += unit.health

        for unit in unitsP2_Healths:
            totalHealthP2 += unit.health

        return (100*VP1 + 100*TP1 + 100*FP1 +   AIP1 + totalHealthP1) - (100*VP2 + 100*TP2 + 100*FP2 +   AIP2 + totalHealthP2)

    def test_move(self, coords: CoordPair) -> Tuple[bool, str]:
        """Validate and perform a move expressed as a CoordPair. TODO: WRITE MISSING CODE!!!"""
        player_unit = self.get(coords.src)

        if self.is_valid_move(coords):

            move = self.move_Type(coords)

            if move == 'Move':
                self.set(coords.dst, self.get(coords.src))
                self.set(coords.src, None)
                return (True, "")

            if move == 'Attack' and self.check_IsCombatState(coords):

                adversary_unit = self.get(coords.dst)

                self.mod_health(coords.src, -adversary_unit.damage_amount(player_unit))
                self.mod_health(coords.dst, -player_unit.damage_amount(adversary_unit))

                if not player_unit.is_alive():
                    self.remove_dead(coords.src)

                if not adversary_unit.is_alive():
                    self.remove_dead(coords.dst)

                return (True, "Damage Dealt")

            if move == 'Self-Destruct':
                self.mod_health(coords.src, -player_unit.health)
                for surrounding in coords.src.iter_range(1):
                    unit = self.get(surrounding)
                    if unit is not None:
                        self.mod_health(surrounding, -2)
                        if unit.health == 0:
                            self.remove_dead(surrounding)

                self.remove_dead(coords.src)
                return (True, "Unit has self-destructed")

            if move == 'Repair' and self.can_Repair(coords):
                unit_to_heal = self.get(coords.dst)

                self.mod_health(coords.dst, player_unit.repair_amount(unit_to_heal))
                return (True, "Restored Health")

        return (False, "invalid move")

    def minimax(self, game, depth, maximizing_Player, alpha, beta):
        start_time = time.time()
        if depth == 0 or game.has_winner() or game.stats.total_seconds == game.options.max_time or game.turns_played == game.options.max_turns:
            # Which Heuristic to Use
            if game.options.heuristic == 'e0':
                return game.heuristic_0(game)
            elif game.options.heuristic == 'e1':
                return game.heuristic_1(game)
            else:
                return game.heuristic_2(game)

        if maximizing_Player:
            max_eval = MIN_HEURISTIC_SCORE
            for move in game.move_candidates():
                game_clone = game.clone()
                game_clone.test_move(move)
                self.stats.total_seconds = self.stats.total_seconds + time.time() - start_time

                if self.stats.total_seconds >= game.options.max_time:
                    break
                eval = game.minimax(game_clone, depth - 1, False, alpha, beta)
                game.stats.cumulative_evals += 1
                max_eval = max(max_eval, eval)
                alpha = max(alpha, eval)

                if game.options.alpha_beta and beta <= alpha:
                    break

            return max_eval

        else:
            min_eval = MAX_HEURISTIC_SCORE
            for move in game.move_candidates():
                game_clone = game.clone()
                game_clone.test_move(move)
                self.stats.total_seconds = self.stats.total_seconds + time.time() - start_time

                if self.stats.total_seconds >= game.options.max_time:
                    break
                eval = game.minimax(game_clone, depth - 1, True, alpha, beta)
                game.stats.cumulative_evals += 1

                min_eval = min(min_eval, eval)
                beta = min(beta, eval)

                if game.options.alpha_beta and beta <= alpha:
                    break

            return min_eval

    # --------------------------------------------------------------------------------------------#
    def suggest_move(self) -> CoordPair | None:
        start_time = time.time()
        """Suggest the next move using minimax alpha beta. TODO: REPLACE RANDOM_MOVE WITH PROPER GAME LOGIC!!!"""
        recommended_move = None
        best_heuristic_score = -MAX_HEURISTIC_SCORE
        alpha = -MAX_HEURISTIC_SCORE
        beta = MAX_HEURISTIC_SCORE

        for move in self.move_candidates():
            game_clone = self.clone()
            game_clone.test_move(move)

            heuristic_score = self.minimax(game_clone, self.options.max_depth, False, alpha, beta)

            if heuristic_score > best_heuristic_score:
                best_heuristic_score = heuristic_score
                recommended_move = move

            alpha = max(alpha, heuristic_score)

            self.stats.total_seconds = self.stats.total_seconds + time.time() - start_time
            if self.stats.total_seconds >= self.options.max_time:
                break

        self.stats.total_seconds = self.stats.total_seconds + time.time() - start_time
        self.stats.heuristic_score = best_heuristic_score
        return recommended_move

    def post_move_to_broker(self, move: CoordPair):
        """Send a move to the game broker."""
        if self.options.broker is None:
            return
        data = {
            "from": {"row": move.src.row, "col": move.src.col},
            "to": {"row": move.dst.row, "col": move.dst.col},
            "turn": self.turns_played
        }
        try:
            r = requests.post(self.options.broker, json=data)
            if r.status_code == 200 and r.json()['success'] and r.json()['data'] == data:
                # print(f"Sent move to broker: {move}")
                pass
            else:
                print(f"Broker error: status code: {r.status_code}, response: {r.json()}")
        except Exception as error:
            print(f"Broker error: {error}")

    def get_move_from_broker(self) -> CoordPair | None:
        """Get a move from the game broker."""
        if self.options.broker is None:
            return None
        headers = {'Accept': 'application/json'}
        try:
            r = requests.get(self.options.broker, headers=headers)
            if r.status_code == 200 and r.json()['success']:
                data = r.json()['data']
                if data is not None:
                    if data['turn'] == self.turns_played + 1:
                        move = CoordPair(
                            Coord(data['from']['row'], data['from']['col']),
                            Coord(data['to']['row'], data['to']['col'])
                        )
                        print(f"Got move from broker: {move}")
                        return move
                    else:
                        # print("Got broker data for wrong turn.")
                        # print(f"Wanted {self.turns_played+1}, got {data['turn']}")
                        pass
                else:
                    # print("Got no data from broker")
                    pass
            else:
                print(f"Broker error: status code: {r.status_code}, response: {r.json()}")
        except Exception as error:
            print(f"Broker error: {error}")
        return None


##############################################################################################################

def main():
    # parse command line arguments
    parser = argparse.ArgumentParser(
        prog='ai_wargame',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--max_depth', type=int, help='maximum search depth')
    parser.add_argument('--max_turns', type=int, help='Maximum number of turns')
    parser.add_argument('--max_time', type=float, help='maximum search time')
    parser.add_argument('--game_type', type=str, default="auto", help='game type: auto|attacker|defender|manual')
    parser.add_argument('--broker', type=str, help='play via a game broker')
    parser.add_argument('--minimax', type=bool, default=True, help='Use of Minimax')
    parser.add_argument('--alpha_beta', type=bool, default=True, help='Use of Alpha-beta')
    parser.add_argument('--heuristic', type=str, help='Use of Alpha-beta')
    args = parser.parse_args()

    # parse the game type
    if args.game_type == "attacker":
        game_type = GameType.AttackerVsComp
    elif args.game_type == "defender":
        game_type = GameType.CompVsDefender
    elif args.game_type == "manual":
        game_type = GameType.AttackerVsDefender
    else:
        game_type = GameType.CompVsComp

    # set up game options
    options = Options(game_type=game_type)

    # override class defaults via command line options
    if args.max_depth is not None:
        options.max_depth = args.max_depth
    if args.max_time is not None:
        options.max_time = args.max_time
    if args.broker is not None:
        options.broker = args.broker

    # create a new game
    game = Game(options=options)

    game.create_File()

    # the main game loop
    while True:
        print()
        print(game)
        winner = game.has_winner()
        if winner is not None:
            print(f"{winner.name} wins!")
            break
        if game.options.game_type == GameType.AttackerVsDefender:
            game.human_turn()
        elif game.options.game_type == GameType.AttackerVsComp and game.next_player == Player.Attacker:
            game.human_turn()
        elif game.options.game_type == GameType.CompVsDefender and game.next_player == Player.Defender:
            game.human_turn()
        else:
            player = game.next_player
            move = game.computer_turn()
            if move is not None:
                game.post_move_to_broker(move)
            else:
                print("Computer doesn't know what to do!!!")
                exit(1)


##############################################################################################################

if __name__ == '__main__':
    main()
