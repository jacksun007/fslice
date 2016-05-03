/* Copyright 2015 Peter Goodman (peter@trailofbits.com), all rights reserved. */

#include <cstdint>
#include <cstring>
#include <unordered_map>
#include <iostream>
#include <fstream>
#include <utility>
#include <set>
#include <vector>
#include <cerrno>
#include <sstream>
#include <algorithm>

#define NON_TAGGED_PHY_ADDR 999999
// Attribute packed is for space compaction. Any object instance created for Taint 
// requires exactly 64 bits. If packed was not used, each attribute of the structure
// would take 4 bytes.

template<typename T>
std::string tostring(const T& t) {
	std::ostringstream ss;
	ss << t;
	return ss.str();
}

// Attribute packed is for space compaction. Any object instance created for Taint 
// requires exactly 64 bits. If packed was not used, each attribute of the structure
// would take 4 bytes.

struct Taint {
  uint64_t id:32;
  uint64_t offset:31;	// S.J. number of bytes following the address that 
			// have the same taint value as start address.
  bool is_obj:1;	// S.J. Is true for objects allocated on heap
	uint64_t phy_addr;
} __attribute__((packed));

struct SaveErrno {
  int no;
  SaveErrno(void)
      : no(errno) {}
  ~SaveErrno(void) {
    errno = no;
  }
};

// Try to merge things like binary operators, constants, and memory loads
// into single taint nodes.
#define CACHE 1
#define VALUE_CACHE 1
#define OP_CACHE 1
#define BLOCKS_CACHE 0

// Treat heap-allocated memory objects as special intermediate objects.
#define MEM false

static Taint gArgs[16] = {{0,0,false,NON_TAGGED_PHY_ADDR}};
static Taint gReturn = {0,0,false,NON_TAGGED_PHY_ADDR};

// Unordered map - helps retrieve Taint values faster. Does not sort the values,
// keeps buckets built in the form of a hash.
static std::unordered_map<uint64_t,Taint> gShadow;
static std::unordered_map<uint64_t,Taint> gValues;
static std::unordered_map<uint64_t,Taint> gObjects;

static std::set<uint64_t> gPrintedBlocks;
static std::unordered_map<uint64_t,Taint> gBlocks;
static std::vector<uint32_t> gBlockTaintIds;
static std::unordered_map<uint64_t,uint64_t> gPrevBlock;
// op = char value. every op has a <object, taint> value
static std::unordered_map<const char *,std::unordered_map<uint64_t,Taint>> gBinaryOps;
static unsigned gId = 1;

extern "C" Taint __fslice_value(uint64_t);

static std::string TaintAsString(Taint t) {
	return "Taint<" + tostring(t.id) + ", " + tostring(t.offset) + ", "
			+ tostring(t.is_obj) + ">";
}

// Load a taint from the shadow memory.
// We create an object hash from the address given to us. We then
// search for the object hash in our Shadow unordered list. If we get it, we 
// return the taint value. If not, we create a taint value and print that 
// out to the graph file.


static Taint Load(uint64_t addr, uint64_t size) {
  SaveErrno save_errno;
//std::cerr << "# Invoking Load(" << addr << ", " << size << ")\n";

#if CACHE
  // So this isn't super great, but it's sufficient for now. Hopefully there
  // are no collisions!
  uint64_t obj_hash = 0;
  for (auto i = 0U; i < size; ++i) {
    const auto mt = gShadow[addr + i];
    obj_hash = ((obj_hash ^ mt.id) << 27) | ((obj_hash >> 19) ^ mt.offset);
  }

  auto &t = gObjects[obj_hash];
  if (t.id) return t;
	
	// avoid multiple taint assignments, if new taint and old taint 
	// are of the same size

	bool assignNewTaint = false;
	uint32_t tid;
	tid = gShadow[addr].id;
	// check if taints for bytes addr to addr+size have same taint id
  for (auto i = 1U; i < size; ++i) {
    const auto mt = gShadow[addr + i];
		if (tid != mt.id){
			assignNewTaint = true;	
			std::cerr << " #XXX assigned new taint id = " << tid << " taint id checked for = " << mt.id << std::endl;
			break;
		}
  }

	// check if previous taint size is not greater than size bytes
	// that are loaded (sent as argument)
	// first see if the next address byte is tainted. if yes, check if its
	// id is same, but offset is not 0, since offset 0 would mean the next
	// <addr+size, addr + 2*size -1> bytes have same type as <addr,addr+size-1>
	if(!assignNewTaint){
		if (gShadow.find(addr+size)!= gShadow.end() && 
					gShadow[addr+size].id == tid && gShadow[addr+size].offset != 0){
			std::cerr << " #YYY assigned new taint id = " << tid << " taint id checked for = " << gShadow[addr+size].id << std::endl;
			assignNewTaint = true;
		}
	}

	// check if Taint is a block taint. If yes, assign a new taint.
	if(!assignNewTaint){	
		if(std::find(gBlockTaintIds.begin(), gBlockTaintIds.end(),tid) != gBlockTaintIds.end())
			assignNewTaint = true;
	}

	if(!assignNewTaint)
		return gShadow[addr];

  t = {gId++, 0, false, NON_TAGGED_PHY_ADDR};
#else
  Taint t = {gId++, 0, false,NON_TAGGED_PHY_ADDR};
#endif
  auto sep = ",";
  std::cerr << "t" << t.id << "=O(" << t.id;
  for (auto i = 0U; i < size; ++i) {
    const auto mt = gShadow[addr + i];
    std::cerr << sep << "t" << mt.id << "[" << mt.offset << "]";
    //sep = ",";
  }
  std::cerr << ") # Load(" << addr << ", " << size << ")" << std::endl;
  return t;
}

// Store a taint to the shadow memory.
// If the address is already tainted. Print it.
// If not, add a taint value to the address.

// addr and phy_addr in Taint t are different
// addr is in memory address. phy_addr is the 
// address on disk

static void Store(uint64_t addr, uint64_t size, Taint t) {
  SaveErrno save_errno;
  std::cerr << "# Invoking Store(" << addr << ", " << size << ", "
			<< TaintAsString(t) << ")" << std::endl;

  for (auto i = 0U; i < size; ++i) {
    auto &et = gShadow[addr + i];
    if (et.is_obj) {
      std::cerr << "t" << et.id << "[" << et.offset << "]=t" << t.id
                << "[" << (t.offset + i) << "] # Store::is_obj equals true."
                << std::endl;
    } else {
        if(t.phy_addr == NON_TAGGED_PHY_ADDR)
      	  et = {t.id, t.offset + i, false, NON_TAGGED_PHY_ADDR}; // should be `taint.offset + i`?
        else
      	  et = {t.id, t.offset + i, false, t.phy_addr + i}; // should be `taint.offset + i`?
    }
  }
}

#define LOAD_STORE(size) \
  extern "C" Taint __fslice_load ## size (uint64_t addr) { \
    return Load(addr, size); \
  } \
  extern "C" void __fslice_store ## size (uint64_t addr, Taint taint) { \
    Store(addr, size, taint); \
  }

// Expands into __fslice_load1 (addr) { return Load (addr, 1) };
//          and __fslice_store1 (addr, Taint taint) { return Store (addr, 1, taint) };
// basically, size can only be 1,2,4,8,16,32 or 64.   

LOAD_STORE(1)
LOAD_STORE(2)
LOAD_STORE(4)
LOAD_STORE(8)
LOAD_STORE(16)
LOAD_STORE(32)
LOAD_STORE(64)

// initialize gArgs and gReturn to 0. return value in gReturn

extern "C" Taint __fslice_load_ret(void) {
  memset(gArgs, 0, sizeof gArgs);
  const auto t = gReturn;
  gReturn = {0,0,false,NON_TAGGED_PHY_ADDR};
  return t;
}

// initialize gArgs. Initialize gReturn with tainted value.

extern "C" void __fslice_store_ret(Taint taint) {
  memset(gArgs, 0, sizeof gArgs);
  gReturn = {taint.id, taint.offset, false, taint.phy_addr};
}

// get tainted value from gArgs. return tainted value. 

extern "C" Taint __fslice_load_arg(uint64_t i) {
  const auto t = gArgs[i];
  gArgs[i] = {0,0,false,NON_TAGGED_PHY_ADDR};
  return t;
}

// store tainted value in gArgs ordered list.

extern "C" void __fslice_store_arg(uint64_t i, Taint taint) {
  gArgs[i] = {taint.id, taint.offset, false, taint.phy_addr};
}

extern "C" void *__fslice_memset(void *dst, int val, uint64_t size) {
	SaveErrno save_errno;
  std::cerr << "# Invoking __fslice_memset(" << dst << ", " << val << ", " << size << ")\n";
  const auto t = __fslice_load_arg(1); // from gArgs unoredered map, load 1st element's taint value
					// into t, and then initialize gArgs[1] to 0,0,false.
  const auto daddr = reinterpret_cast<uint64_t>(dst);
  for (auto i = 0U; i < size; ++i) {
      gShadow[daddr + i] = {t.id, t.offset + i, false, NON_TAGGED_PHY_ADDR};
  }                                       // daddr+ size with taint id t.
  __fslice_store_ret({0,0,false,NON_TAGGED_PHY_ADDR}); // gReturn is initialized with {0,0,false}
	return memset(dst, val, size);          // initialize the address with val.
					// the main purpose why memset was called!
}

// taint destination address with the same value as that at source
extern "C" void *__fslice_memmove(void *dst, const void *src, uint64_t size) {
  SaveErrno save_errno;
  std::cerr << "# Invoking __fslice_memmove(" << dst << ", " << src << ", " << size
		    << ")\n";

  const auto daddr = reinterpret_cast<uint64_t>(dst);
  const auto saddr = reinterpret_cast<uint64_t>(src);
  for (auto i = 0U; i < size; ++i) {
    const auto bt = gShadow[saddr + i];
    gShadow[daddr + i] = {bt.id, bt.offset, false,bt.phy_addr + i};
  }
  std::cerr << "#DSTRUCT:"<< "Addr=" << gShadow[daddr].phy_addr << ":Size|" << size << std::endl;
  __fslice_store_ret({0,0,false,NON_TAGGED_PHY_ADDR}); // initialize all gArgs. intialize gRet to 0,0,false
  return memmove(dst, src, size);
}

extern "C" void *__fslice_memcpy(void *dst, const void *src, uint64_t size) {
  return __fslice_memmove(dst, src, size);
}

extern "C" char *__fslice_strcpy(char *dst, const char *src) {
  return reinterpret_cast<char *>(__fslice_memmove(dst, src, strlen(src) + 1));
}

// initialize all taint values in global Shadow memory as false
extern "C" void __fslice_bzero(void *dst, uint64_t size) {
  const auto daddr = reinterpret_cast<uint64_t>(dst);
  for (auto i = 0U; i < size; ++i) {
    gShadow[daddr + i] = {0,0,false,NON_TAGGED_PHY_ADDR};
  }
  __fslice_store_ret({0,0,false,NON_TAGGED_PHY_ADDR}); // initialize gArgs as false. initialize gReturn as false
  memset(dst, 0, size);
}

extern "C" void *__fslice_malloc(uint64_t size) {
  auto ptr = calloc(1, size);
  const auto addr = reinterpret_cast<uint64_t>(ptr);
  Taint t = {gId++, 0,false,NON_TAGGED_PHY_ADDR};

  std::cerr << "t" << t.id << "=M(" << size << ", " << MEM << ", " << t.id
			<< ",t" << __fslice_load_arg(0).id << ")" << std::endl;

  for (auto i = 0U; i < size; ++i) {
    gShadow[addr + i] = {t.id, i, MEM, t.phy_addr}; // MEM -treat heap allocated objects as separate objects
  }					// by default it is false.
  __fslice_store_ret({0,0,false, NON_TAGGED_PHY_ADDR});	// init gArgs list and gReturn with 0,0,false
  return ptr;
}

extern "C" void *__fslice_calloc(uint64_t num, uint64_t size) {
  auto ptr = calloc(num, size);
  const auto addr = reinterpret_cast<uint64_t>(ptr);
  Taint t = {gId++, 0,false, NON_TAGGED_PHY_ADDR};
  std::cerr << "t" << t.id << "=M(" << size << ", " << MEM << ", " << t.id
			<< ",t" << __fslice_load_arg(0).id << ",t"
            << __fslice_load_arg(1).id << ")" << std::endl;

  for (auto i = 0U; i < num * size; ++i) {
    gShadow[addr + i] = {t.id, i, MEM, t.phy_addr};
  }
  __fslice_store_ret({0,0,false, NON_TAGGED_PHY_ADDR});	// init gArgs list and gReturn with 0,0,false
  return ptr;
}

extern "C" Taint __fslice_value(uint64_t val) {
	SaveErrno save_errno;
#if VALUE_CACHE
	auto &t = gValues[val];
	if (/*val && */ !t.id) {
		t = { gId++, 0, false, NON_TAGGED_PHY_ADDR };
		std::cerr << "t" << t.id << "=V(" << val << ", " << t.id << ")" << " # "
				<< TaintAsString(t) << std::endl;
	}

	return t;
#else
	/*if (val) { */
		Taint t = {gId++, 0, false, NON_TAGGED_PHY_ADDR};
		std::cerr << "t" << t.id << "=V(" << val << ", " << t.id << ")" << " # " << TaintAsString(t) << std::endl;
		return t;
	/*} else {
		return {0, 0, false};
	}*/
#endif
}

// A is a binary symbol. we add taint id gId++ to gBinaryOps[operation][t1,t2]
// on the taint log file, we print gId=A(t1,t2).

extern "C" Taint __fslice_op2(const char *op, Taint t1, Taint t2) {
  SaveErrno save_errno;
#if OP_CACHE
  const auto id = t1.id | (static_cast<uint64_t>(t2.id) << 32);
  auto &t = gBinaryOps[op][id];
  if (!t.id) {
    t = {gId++, 0, false, NON_TAGGED_PHY_ADDR};
    std::cerr << "t" << t.id << "=A(\"" << op << "\",t" << t1.id
              << ",t" << t2.id << ", " << t.id << ")" << std::endl;
  }
#else
  Taint t = {gId++, 0, false, NON_TAGGED_PHY_ADDR};
  std::cerr << "t" << t.id << "=A(\"" << op << "\",t" << t1.id
            << ",t" << t2.id << ", " << t.id << ")" << std::endl;
#endif
  return t;
}

// nr - physical address number of the block.
// size - granularity at which data is being read into memory. 
// Only in GetBlock does the tainting of actual data blocks happen.


static Taint GetBlock(uint64_t size, uint64_t nr) {
	Taint t = { 0, 0, false };
#if BLOCKS_CACHE
	t = gBlocks[nr];
#endif
	if (!t.id) {
		t = {gId++, 0, false, nr * size};
		gBlockTaintIds.push_back(t.id);
		const auto st = __fslice_load_arg(1);  // Taint for the size :-)
		const auto nt = __fslice_load_arg(2);  // Taint for the block number :-)
		std::cerr << "t" << t.id << "=B(" << size << "," << nr << ",t" << st.id
				<< ",t" << nt.id << ", " << t.id << ") # GetBlock(" << size
				<< ", " << nr << ")" << std::endl;
		__fslice_store_ret( { 0, 0, false, NON_TAGGED_PHY_ADDR});
	} else {
		std::cerr << "# Block " << nr << " is already tainted as: t" << t.id
				<< std::endl;
	}
#if BLOCKS_CACHE
	gBlocks[nr] = t;
	gBlockTaintIds.push_back(t.id);
#endif
	return t;
}

// Go through each of the blocks, and populate gShadow with the block ids of read objects
// if the first block does not have a taint, get a taint value for the block.
// once the taint value is obtained, iterate and assign all the accessed blocks the same
// taint id.

extern "C" void __fslice_read_block(uint64_t addr, uint64_t size, uint64_t nr) {
  SaveErrno save_errno;
  std::cerr << "# Invoking __fslice_read_block(" << addr << ", " << size
		    << ", " << nr << ")\n";

  auto t = GetBlock(size, nr);
  for (auto i = 0U; i < size; ++i) {
    gShadow[addr + i] = {t.id, i, false, (nr *size) + i};
  }
}

extern "C" void __fslice_print_func(void *ptr) {
  if(ptr!=NULL)
    std::cerr << "# "<< (char *)ptr << "()" << std::endl;
}

// Mark some memory as a block.
// if the block that is being written is already tainted, write trace.
// if the block is not tainted, continue.

extern "C" void __fslice_write_block(uint64_t addr, uint64_t size, uint64_t nr) {
  SaveErrno save_errno;
  std::cerr << "# Invoking __fslice_write_block(" << addr << ", " << size << ", " << nr
			<< ")\n";

  auto t = GetBlock(size, nr);
  for (auto i = 0UL; i < size; ++i) {
    const auto bt = gShadow[addr + i];
    if (!bt.id || (t.id == bt.id && i == bt.offset)) {
        if (!bt.id) {
			std::cerr << "# __fslice_write_block(" << addr << ", " << size
					  << ", " << nr << ")::gShadow[" << (addr + i)
					  << "] does not contain a taint value!" << std::endl;
		}
		if ((t.id == bt.id && i == bt.offset)) {
			std::cerr << "# __fslice_write_block_(" << addr << ", " << size
					  << ", " << nr << ")::gShadow[" << (addr + i)
					  << "] contains the same taint value!" << std::endl;
		}
        continue;
    }
    std::cerr << "t" << t.id << "[" << i << "]=t" << bt.id << "["
			  << bt.offset << "] # fslice_write_block(" << addr << ", "
			  << size << ", " << nr << ")" << std::endl;
  }
}

// Mark some memory as a name.
// S.J. add a name to memory location.
// populate gShadow hash with new taint Id.

extern "C" void __fslice_name(uint64_t addr, uint64_t len) {
  SaveErrno save_errno;
  Taint t = {gId++, 0, false, NON_TAGGED_PHY_ADDR};
  std::cerr << "t" << t.id << "=N(" << len << ", " << t.id << ")"
			<< std::endl;

  for (auto i = 0U; i < len; ++i) {
    gShadow[addr + i] = {t.id, i, false, t.phy_addr};
  }
}

// Mark some memory as data.
// S.J. if the taint id exists, print the taint as that for a data block.
// if taint tid does not exist, populate gShadow of that addr with the same tid
// generated for all accessed data.
extern "C" void __fslice_data(uint64_t addr, uint64_t len) {
  SaveErrno save_errno;
  Taint t = {gId++, 0, false, NON_TAGGED_PHY_ADDR};
  std::cerr << "t" << t.id << "=D(" << len << ", " << t.id << ")"
			<< std::endl;

  for (auto i = 0U; i < len; ++i) {
    auto &bt = gShadow[addr + i];
    if (bt.id) {
      std::cerr << "t" << t.id << "[" << i << "]=t" << bt.id
                << "[" << bt.offset << "]" << std::endl;
    }
    bt = {t.id, i, false, t.phy_addr};	// XXX unsure about non_tagged_phy_addr
  }
}

extern "C" void __fslice_clear() {
//	printf("%s\n", __func__);
	gShadow.clear();
	gObjects.clear();
	gValues.clear();
	gBlocks.clear();
	gBlockTaintIds.clear();
	gPrevBlock.clear();
	gBinaryOps.clear();
	gId=1;		
}
