import argparse
import collections
import json
import time
import sys

parser = argparse.ArgumentParser(description='Calculate output graph.')
parser.add_argument('--metadata', dest='PRINT_METADATA', const=True, default=False,
                    nargs='?', help='Print metadata.')
parser.add_argument('--graph', dest='PRINT_GRAPH', const=True, default=False,
                    nargs='?', help='Print the output graph.')
parser.add_argument('--enum', dest='DETECT_ENUMS', const=True, default=False,
                    nargs='?', help='Detect possible enums.')
parser.add_argument('--verbose', dest='VERBOSE', const=True, default=False,
                    nargs='?', help='Print information in detail.')
parser.add_argument('--debug', dest='DEBUG', const=True, default=False,
                    nargs='?', help='Print debug information.')

args = parser.parse_args()

# Constants.
POINTER_SIZE = 4
BLOCK_SIZE = 64

# Data types.
pointerList = collections.defaultdict(list)
pointerSet = set()
valueSet = collections.defaultdict(int)
dataSet = set()
nameSet = set()

# Block types.
directory_entry_blocks = collections.defaultdict(list)
data_blocks = set()
name_bytes_per_block = collections.defaultdict(list)
data_bytes_per_block = collections.defaultdict(list)


def isDataBlock(block_number):
    if args.DEBUG:
        print("[DEBUG, {}]: Checking for data blocks, Block {} contains [{}, {}]".\
            format(time.time(), block_number,
                   len(name_bytes_per_block[block_number]),
                   len(data_bytes_per_block[block_number])))

    if len(name_bytes_per_block[block_number]) > 0:
        return False
    elif len(data_bytes_per_block[block_number]) > 0:
        return True
    else:
        return False


class Base(object):
    def __init__(self, taintID=""):
        self.size = 1
        self.byte_sources = {}
        self.taintID = taintID
        self.seen = False

    def __getitem__(self, byte):
        self.size = max(self.size, byte + 1)
        return Select(self, byte)

    def __setitem__(self, byte, val):
        self.byte_sources[byte] = val

    def getName(self):
        return self.__class__.__name__

    def Label(self):
        return "n{}".format(id(self))

    def PrintByteSources(self, next, edges):
        for i, s in self.byte_sources.items():
            next.add(s)
            edges.add("{}:b{} -> {} [ label=\"t{}\" ];".format(self.Label(), i, s.Label(), s.taintID))

    def _bytes(self):
        return "|".join("<b{}>".format(i) for i in range(self.size))

    def markPointer(self, byte, block_number):
        pass

    def markPointers(self, block_number):
        pass

    def getValue(self):
        return None

    def getByte(self, byte):
        return self.byte_sources[byte]


class Select(Base):
    def __init__(self, parent, byte):
        Base.__init__(self, parent.taintID)
        self.parent = parent
        self.byte = byte
        self.seen = False

    def markPointers(self, block_number):
        if self.seen:
            return

        self.seen = True

        if self.parent.getName() == 'B':
            self.parent.markPointer(self.byte, block_number)
        else:
            self.parent.markPointers(block_number)

    def getValue(self):
        if self.parent.getName() == 'B':
            offset = (self.parent.nr * self.parent.size) + self.byte
            if offset in valueSet:
                return valueSet[offset]
            else:
                return None
        else:
            return self.parent.getValue()

    def Print(self, next, edges):
        next.add(self.parent)

    def Label(self):
        return "{}:b{}".format(self.parent.Label(), self.byte)


class V(Base):
    def __init__(self, val, taintID):
        Base.__init__(self, taintID)
        self.val = val
        self.usedAsPointer = False

    def Print(self, next, edges):
        print("{} [label=\"{{{{{}}}|{}}}\"];".format(self.Label(), self._bytes(), self.val))

    def getValue(self):
        return self.val


class A(Base):
    def __init__(self, op, a, b, taintID):
        Base.__init__(self, taintID)
        self.op = op
        self.left = a
        self.right = b

    def markPointers(self, block_number):
        if self.seen:
            return

        self.seen = True
        self.left.markPointers(block_number)
        self.right.markPointers(block_number)

    def Print(self, next, edges):
        if self.left.getName() == 'V':
            LL = str(self.left.val)
        else:
            next.add(self.left)
            LL = "<left>"
            edges.add("{}:left -> {} [ label=\"t{}\" ];".format(self.Label(), self.left.Label(), self.left.taintID))

        if self.right.getName() == 'V':
            RL = str(self.right.val)
        else:
            next.add(self.right)
            RL = "<right>"
            edges.add("{}:right -> {} [ label=\"t{}\" ];".format(self.Label(), self.right.Label(), self.right.taintID))

        print("{} [color=blue label=\"{{ {{ {} }} | {{ {} | t{} }} | {{{}|{}}} }}\"];".format(
            self.Label(), self._bytes(), self.op, self.taintID, LL, RL))

    def getValue(self):
        lvalue = self.left.getValue()
        rvalue = self.right.getValue()
        if isinstance(lvalue, int) and isinstance(rvalue, int):
            if self.op is "add":
                return lvalue + rvalue
            elif self.op is "mul":
                return lvalue * rvalue
            elif self.op is "sdiv" or self.op is "udiv":
                return lvalue / rvalue
            elif self.op is "shl":
                return lvalue << rvalue
            elif self.op is "xor":
                return lvalue ^ rvalue
            else:
                print("[DEBUG, {}]: Undefined Binary Operation {} for taint {}"
                      .format(time.time(), self.op, self.taintID))
                return None
        else:
            return None


class O(Base):
    def __init__(self, _, taintID, *bytes):
        Base.__init__(self, taintID)
        self.bytes = bytes
        self.size = len(self.bytes)

    def markPointers(self, block_number):
        # If the object has already been processed, then return.
        if self.seen:
            return

        # Check for pointers only in objects whose size equals to POINTER_SIZE.
        if self.size != POINTER_SIZE:
            return

        # Verify that the specified objects contains four consecutive bytes
        # that correspond to the same taint ID.
        for i in range(1, len(self.bytes)):
            # The taint ID must be the same in all POINTER_SIZE bytes.
            if self.bytes[i].taintID != self.bytes[i-1].taintID:
                self.seen = True
                return

            # All POINTER_SIZE bytes must be consecutive.
            if (self.bytes[i].byte - 1) != self.bytes[i-1].byte:
                self.seen = True
                return

        # Mark the object as processed, in order to speed up the recursion.
        self.seen = True

        for i in range(0, self.size):
            self.__getitem__(i).markPointers(block_number)

    def __getitem__(self, byte):
        self.size = max(self.size, byte + 1)
        if byte < len(self.bytes):
            return self.bytes[byte]
        else:
            return Select(self, byte)

    def getValue(self):
        return self.bytes[0].getValue()

    def Print(self, next, edges):
        print("{} [label=\"{{{{}}|{{{}}}}}\"];".format(self.Label(), self._bytes()))
        for i, b in enumerate(self.bytes):
            next.add(b)
            edges.add("{}:b{} -> {} [ label=\"t{}\" ];".format(self.Label(), i, b.Label(), b.taintID))


class B(Base):
    BLOCKS = []

    def __init__(self, size, nr, block_size, block_nr, taintID):
        Base.__init__(self, taintID)
        self.size = size
        self.nr = nr
        self.block_size = block_size
        self.block_nr = block_nr
        self.BLOCKS.append(self)
        self.data_bytes = 0
        self.name_bytes = 0

        # Search for on-disk pointers by following taints in
        # a backwards fashion.
        block_size.markPointers(self.nr)
        block_nr.markPointers(self.nr)

    def __setitem__(self, byte, val):
        Base.__setitem__(self, byte, val)

        if val.parent.getName() == 'V':
            valueSet[(self.nr * self.size) + byte] = val.parent.val
        elif val.parent.getName() == 'A':
            operatorValue = val.parent.getValue()
            if operatorValue is not None:
                valueSet[(self.nr * self.size) + byte] = operatorValue
        elif val.parent.getName() == 'B':
            byte_value = val.getValue()
            if byte_value is not None:
                valueSet[(self.nr * self.size) + byte] = byte_value
        #
        # elif val.parent.getName() == 'D':
        #     if args.DEBUG:
        #         print("[DEBUG, {}]: Inside block {} with offset {} and value {} and {}".\
        #             format(time.time(), self.nr, byte, val.taintID, val.parent.getByte(byte).parent.taintID))
        #
        #     if val.parent.getByte(val.byte).parent.getName() == 'N':
        #         nameSet.add((self.nr * self.size) + byte)
        #         directory_entry_blocks[self.nr].append(self)
        #         name_bytes_per_block[self.nr].append(byte)
        #     else:
        #         dataSet.add((self.nr * self.size) + byte)
        #         data_bytes_per_block[self.nr].append(byte)
        #
        elif args.DEBUG:
                print("[DEBUG, {}]: Ignoring type {}({}) in block's {}({}) assignment operator for byte {}.".\
                    format(time.time(), val.parent.getName(), val.parent.taintID, self.nr, self.taintID, byte))

    def markPointer(self, byte, block_number):
        disk_offset = (self.size * self.nr) + byte
        pointerList[block_number].append(disk_offset)

        if args.DEBUG:
            if disk_offset in pointerSet:
                print("[DEBUG, {}]: Byte {} is already marked as part of a pointer.".\
                    format(time.time(), disk_offset))

        pointerSet.add(disk_offset)
        if args.DEBUG:
            print("[DEBUG, {}]: Byte {} was marked as part of a pointer.".format(time.time(), disk_offset))
            print("[DEBUG, {}]: Byte {} in block {} with taintID {} points to block {}".\
                format(time.time(), byte, self.nr, self.taintID, block_number))

    def Print(self, next, edges):
        print("{} [rank=max fillcolor=grey style=filled label=\"{{{{{}}}|{{<size>size = {} | <nr>nr = {} | <tid>tid = {}}}}}\"];" \
            .format(self.Label(), self._bytes(), self.size, self.nr, self.taintID))

        if self.block_size.getName() != 'V':
            next.add(self.block_size)
            edges.add("{}:size -> {} [ label=\"t{}\" ];"
                      .format(self.Label(), self.block_size.Label(), self.block_size.taintID))

        if self.block_nr.getName() != 'V':
            next.add(self.block_nr)
            edges.add("{}:nr -> {} [ label=\"t{}\" ];"
                      .format(self.Label(), self.block_nr.Label(), self.block_nr.taintID))


class NT(Base):
    def __init__(self, taintID):
        Base.__init__(self, taintID)

    def Print(self, next, edges):
        print("{} [fillcolor=yellow2 style=filled label=\"{{{{{}}} | {{<size>size = {} | t{} }}}}\"];" \
            .format(self.Label(), self._bytes(), self.size, self.taintID))


class N(Base):
    def __init__(self, size, taintID):
        Base.__init__(self, taintID)
        self.size = size

    def Print(self, next, edges):
        print("{} [fillcolor=green style=filled label=\"{{{{{}}} | {{<size>size = {} | t{} }}}}\"];" \
            .format(self.Label(), self._bytes(), self.size, self.taintID))


class D(Base):
    def __init__(self, size, taintID):
        Base.__init__(self, taintID)
        self.size = size

    def getByte(self, byte):
        if byte in self.byte_sources:
            return self.byte_sources[byte]
        else:
            return self[byte]

    def Print(self, next, edges):
        print("{} [fillcolor=orange style=filled label=\"{{{{{}}} | {{<size>size = {} | t{} }}}}\"];" \
            .format(self.Label(), self._bytes(), self.size, self.taintID))


class S(Base):
    def __init__(self, size, taintID):
        Base.__init__(self, taintID)
        self.size = size

    def getByte(self, byte):
        if byte in self.byte_sources:
            return self.byte_sources[byte]
        else:
            return self[byte]

    def Print(self, next, edges):
        print("{} [fillcolor=orange style=filled label=\"{{{{{}}} | {{<size>size = {} | t{} }}}}\"];" \
            .format(self.Label(), self._bytes(), self.size, self.taintID))


class M(Base):
    def __init__(self, size, isObject, taintID, *size_deps):
        Base.__init__(self, taintID)
        self.size = size
        self.isObject = isObject
        self.size_deps = size_deps

    def Print(self, next, edges):
        if (self.isObject):
            print("{} [fillcolor=darkgoldenrod style=filled label=\"{{{{{}}} | {{<size>size = {} | t{} }}}}\"];" \
                .format(self.Label(), self._bytes(), self.size, self.taintID))
        else:
            print("{} [fillcolor=darkorchid2 style=filled label=\"{{{{{}}} | {{<size>size = {} | t{} }}}}\"];" \
                .format(self.Label(), self._bytes(), self.size, self.taintID))

        for dep in self.size_deps:
            next.add(dep)
            edges.add("{}:size -> {} [ label=\"t{}\" ];".format(self.Label(), dep.Label(), self.taintID))


def PrintBlocks():
    # Initialize blocks to be a dictionary of lists.
    # Organize blocks based on their block number.
    blocks = collections.defaultdict(list)
    for b in B.BLOCKS:
        blocks[b.nr].append(b)

    if args.PRINT_METADATA:
        for nr in blocks.keys():
            if isDataBlock(nr):
                data_blocks.add(nr)

        # print(pointerList)
        total_pointers = len(pointerSet)

        # The total number of bytes marked as on-disk pointers must be
        # a multiple of POINTER_SIZE. Otherwise, catch the error and print
        # the current bytes marked as on-disk pointers.
        res = total_pointers % POINTER_SIZE
        if res != 0:
            print("Total pointers: {}".format(total_pointers))
            print("PointerSet: {}".format(sorted(pointerSet)))
            assert(res == 0)

        print("Total pointers: {}".format(total_pointers / POINTER_SIZE))
        if args.VERBOSE:
            # print "PointerSet: {}".format(sorted(pointerSet))
            print("NameSet: {}".format(nameSet))
            print("DataSet: {}".format(dataSet))
            print("ValueSet: {}".format(valueSet))
            print("DataSet per Block: {}".format(data_bytes_per_block))
            print("DEntrySet per Block".format(name_bytes_per_block))
            print("Blocks with directory entries: {}".format(sorted(directory_entry_blocks.keys())))
            print("Datablocks: {}".format(sorted(data_blocks)))
            print("{}".format(sorted(pointerSet)))

    if args.PRINT_GRAPH:
        print("digraph {")
        print("node [shape=record];")
        seen, nodes, edges = set(), set(), set()

        for nr, bs in blocks.items():
            # nr = block number (the key of the dictionary)
            # bs = list of blocks

            if 1 < len(bs):
                # By denoting subgraph as a cluster, the entire drawing of the
                # cluster will be contained within a bounding rectangle.
                print("subgraph cluster{} {{".format(nr))
                print("rankdir=TB;")  # Graph will be laid out from top to bottom.

            for b in bs:
                seen.add(b)  # Mark block as "seen".
                b.Print(nodes, edges)
                b.PrintByteSources(nodes, edges)

            if 1 < len(bs):
                print("}")

        while nodes:
            node = nodes.pop()
            if node not in seen:
                seen.add(node)  # Mark block as "seen" in order not to process it.
                node.Print(nodes, edges)
                node.PrintByteSources(nodes, edges)

        for edge in edges:
            print(edge)

        print("}")

    if args.DETECT_ENUMS:
        blockDPMap = dict()
        with open('testfs_output.dat', 'r') as file:
            blockDPMap = json.load(file)

        # Verify that the input data is correct.
        for block in blockDPMap:
            assert(len(blockDPMap[block]) == BLOCK_SIZE)

        inode_blocks = []
        for i in range(64, 192):
            inode_blocks.append(str(i))

        for block_number in inode_blocks:
            if block_number in blockDPMap:
                block_types = blockDPMap[block_number]
                for i in range(0, BLOCK_SIZE):
                    if block_types[i] == 'D':
                        offset = int(block_number) * BLOCK_SIZE + i
                        if offset in valueSet:
                            block_types[i] = valueSet[offset]

        for offset in pointerSet:
            block_number = str(offset / BLOCK_SIZE)
            block_byte = offset % BLOCK_SIZE

            if block_number not in blockDPMap:
                print("[ERROR, {}]: Block {} is not stored in blockDPMap.".format(time.time(), block_number))
                sys.exit(-1)
            else:
                block_types = blockDPMap[block_number]
                if block_types[block_byte] != 'P':
                    block_types[block_byte] = 'P'
                    print("[INFO, {}]: Byte {} inside block {} was not marked as part of a pointer."
                          .format(time.time(), block_byte, block_number))

        for block_number in inode_blocks:
            if block_number in blockDPMap:
                print('\n------------------------------\nBlock {}:\n{} //\n{}\n------------------------------'
                      .format(block_number, blockDPMap[block_number][:32], blockDPMap[block_number][32:]))

t0 = NT(0)
