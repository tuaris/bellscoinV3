#!/usr/bin/env python3
# Copyright (c) 2014-2019 Daniel Kraft
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.

# Test the merge-mining RPC interface:
# getauxblock, createauxblock, submitauxblock

from test_framework.test_framework import BellscoinTestFramework
from test_framework.util import (
  assert_equal,
  assert_greater_than_or_equal,
  assert_raises_rpc_error,
)

from test_framework.auxpow import reverseHex
from test_framework.auxpow_testing import (
  computeAuxpow,
  getCoinbaseAddr,
  mineAuxpowBlockWithMethods,
)
# Bellscoin
from test_framework.messages import (
  CHAIN_ID,
)
from decimal import Decimal

class AuxpowMiningTest (BellscoinTestFramework):
  def skip_test_if_missing_module(self):
    self.skip_if_no_wallet()

  def set_test_params (self):
    print("----F11")
    self.num_nodes = 2
    print("----F12")
    # Must set '-dip3params=9000:9000' to create pre-dip3 blocks only
    self.extra_args = [[],[]] # ['-dip3params=9000:9000'],['-dip3params=9000:9000']

  def add_options (self, parser):
    self.add_wallet_options(parser)
    parser.add_argument ("--segwit", dest="segwit", default=False,
                         action="store_true",
                         help="Test behaviour with SegWit active")

  def run_test (self):
    # Activate segwit if requested.
    print("----F1")
    if self.options.segwit:
      print("----F2")
      self.generate(self.nodes[0], 500)

    print("----F3")
    # Test with getauxblock and createauxblock/submitauxblock.
    self.test_getauxblock ()
    print("----F4")
    self.test_create_submit_auxblock ()

  def test_common (self, create, submit):
    """
    Common test code that is shared between the tests for getauxblock and the
    createauxblock / submitauxblock method pair.
    """

    # Verify data that can be found in another way.
    auxblock = create ()
    assert_equal (auxblock['chainid'], CHAIN_ID)
    assert_equal (auxblock['height'], self.nodes[0].getblockcount () + 1)
    assert_equal (auxblock['previousblockhash'],
                  self.nodes[0].getblockhash (auxblock['height'] - 1))

    # Calling again should give the same block.
    auxblock2 = create ()
    assert_equal (auxblock2, auxblock)

    # If we receive a new block, the old hash will be replaced.
    self.sync_all ()
    self.generate(self.nodes[1], 1)
    auxblock2 = create ()
    assert auxblock['hash'] != auxblock2['hash']
    assert_raises_rpc_error (-8, 'block hash unknown', submit,
                             auxblock['hash'], "x")

    # Invalid format for auxpow.
    assert_raises_rpc_error (-1, None, submit,
                             auxblock2['hash'], "x")

    # Invalidate the block again, send a transaction and query for the
    # auxblock to solve that contains the transaction.
    self.generate(self.nodes[0], 1)
    addr = self.nodes[1].get_deterministic_priv_key ().address
    txid = self.nodes[0].sendtoaddress (addr, 1)
    self.sync_all ()
    assert_equal (self.nodes[1].getrawmempool (), [txid])
    auxblock = create ()
    target = reverseHex (auxblock['_target'])

    # Cross-check target value with GBT to make explicitly sure that it is
    # correct (not just implicitly by successfully mining blocks for it
    # later on).
    gbt = self.nodes[0].getblocktemplate ({"rules": ["segwit"]})
    tmp = gbt['target'].encode ("ascii")
    assert_equal (target, gbt['target'].encode ("ascii"))

    # Compute invalid auxpow.
    apow = computeAuxpow (auxblock['hash'], target, False)
    res = submit (auxblock['hash'], apow)
    assert not res

    # Compute and submit valid auxpow.
    apow = computeAuxpow (auxblock['hash'], target, True)
    res = submit (auxblock['hash'], apow)
    assert res

    # Make sure that the block is indeed accepted.
    self.sync_all ()
    assert_equal (self.nodes[1].getrawmempool (), [])
    height = self.nodes[1].getblockcount ()
    assert_equal (height, auxblock['height'])
    assert_equal (self.nodes[1].getblockhash (height), auxblock['hash'])

    # Call getblock and verify the auxpow field.
    data = self.nodes[1].getblock (auxblock['hash'])
    assert 'auxpow' in data
    auxJson = data['auxpow']
    assert_equal (auxJson['chainindex'], 0)
    assert_equal (auxJson['merklebranch'], [])
    assert_equal (auxJson['chainmerklebranch'], [])
    assert_equal (auxJson['parentblock'], apow[-160:])

    # Also previous blocks should have 'auxpow', since all blocks (also
    # those generated by "generate") are merge-mined.
    # BELLSCOIN not true, check prev not auxpow
    oldHash = self.nodes[1].getblockhash (100)
    data = self.nodes[1].getblock (oldHash)
    assert 'auxpow' not in data

    # Check that it paid correctly to the first node.
    t = self.nodes[0].listtransactions ("*", 1)
    assert_equal (len (t), 1)
    t = t[0]
    assert_equal (t['category'], "immature")
    assert_equal (t['blockhash'], auxblock['hash'])
    assert t['generated']
    assert_greater_than_or_equal (t['amount'], Decimal ("1"))
    assert_equal (t['confirmations'], 1)

    # Verify the coinbase script.  Ensure that it includes the block height
    # to make the coinbase tx unique.  The expected block height is around
    # 200, so that the serialisation of the CScriptNum ends in an extra 00.
    # The vector has length 2, which makes up for 02XX00 as the serialised
    # height.  Check this.  (With segwit, the height is different, so we skip
    # this for simplicity.)
    if not self.options.segwit:
      blk = self.nodes[1].getblock (auxblock['hash'])
      tx = self.nodes[1].getrawtransaction (blk['tx'][0], True, blk['hash'])
      coinbase = tx['vin'][0]['coinbase']
      assert_equal ("02%02x00" % auxblock['height'], coinbase[0 : 6])

  def test_getauxblock (self):
    """
    Test the getauxblock method.
    """

    create = self.nodes[0].getauxblock
    submit = self.nodes[0].getauxblock
    self.test_common (create, submit)

    # Ensure that the payout address is changed from one block to the next.
    hash1 = mineAuxpowBlockWithMethods (create, submit)
    hash2 = mineAuxpowBlockWithMethods (create, submit)
    self.sync_all ()
    addr1 = getCoinbaseAddr (self.nodes[1], hash1)
    addr2 = getCoinbaseAddr (self.nodes[1], hash2)
    assert addr1 != addr2
    info = self.nodes[0].getaddressinfo (addr1)
    assert info['ismine']
    info = self.nodes[0].getaddressinfo (addr2)
    assert info['ismine']

  def test_create_submit_auxblock (self):
    """
    Test the createauxblock / submitauxblock method pair.
    """

    # Check for errors with wrong parameters.
    assert_raises_rpc_error (-1, None, self.nodes[0].createauxblock)
    assert_raises_rpc_error (-5, "Invalid coinbase payout address",
                             self.nodes[0].createauxblock,
                             "this_an_invalid_address")

    # Fix a coinbase address and construct methods for it.
    addr1 = self.nodes[0].get_deterministic_priv_key ().address

    def create ():
      return self.nodes[0].createauxblock (addr1)
    submit = self.nodes[0].submitauxblock

    # Run common tests.
    self.test_common (create, submit)
    # Ensure that the payout address is the one which we specify
    hash1 = mineAuxpowBlockWithMethods (create, submit)
    hash2 = mineAuxpowBlockWithMethods (create, submit)
    self.sync_all ()
    actual1 = getCoinbaseAddr (self.nodes[1], hash1)
    actual2 = getCoinbaseAddr (self.nodes[1], hash2)
    assert_equal (actual1, addr1)
    assert_equal (actual2, addr1)

    # Ensure that different payout addresses will generate different auxblocks
    addr2 = self.nodes[1].get_deterministic_priv_key ().address
    auxblock1 = self.nodes[0].createauxblock(addr1)
    auxblock2 = self.nodes[0].createauxblock(addr2)
    assert auxblock1['hash'] != auxblock2['hash']

if __name__ == '__main__':
  AuxpowMiningTest (__file__).main ()
