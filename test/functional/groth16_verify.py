#!/usr/bin/env python3
# Copyright (c) 2018-2022 The Bellscoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.
"""Test groth16 arguments.
"""

from test_framework.test_framework import BellscoinTestFramework
from test_framework.util import assert_equal
from decimal import Decimal

class Groth16VerifyTest(BellscoinTestFramework):
    def add_options(self, parser):
        self.add_wallet_options(parser)

    def set_test_params(self):
        self.setup_clean_chain = True
        self.num_nodes = 1
        self.extra_args = [[
            "-walletrejectlongchains=0", "-whitelist=noban@127.0.0.1", "-maxtxfee=0.1"
        ]]
        self.supports_cli = False

    def skip_test_if_missing_module(self):
        self.skip_if_no_wallet()

    def setup_network(self, split=False):
        self.setup_nodes()

    def run_test(self):
        node = self.nodes[0]
        self.generate(node, 1)  # Leave IBD for sethdseed
        print(f"-- 1 - {node.chain}")

        # Create and load the wallet
        self.nodes[0].createwallet(wallet_name='w0', descriptors=True)
        self.nodes[0].setnetworkactive(True)
        w0 = node.get_wallet_rpc('w0')

        # Get a new address and check balance
        address1 = w0.getnewaddress()
        assert_equal(w0.getbalance(), 0.0)
        self.generatetoaddress(node, 50, address1)

        # Example Groth16 proof (replace with actual proof data)
        proof = b'your_groth16_proof_here'

        # Create a raw transaction sending 1 coin to the address
        tx = w0.createrawtransaction([], {address1: 1})
        tx = w0.fundrawtransaction(tx, {'changeAddress': address1})
        tx = w0.signrawtransactionwithwallet(tx['hex'])

        custom_fee_rate = 0.0001  # Lower the fee rate to avoid exceeding limits
        w0.settxfee(custom_fee_rate)
        # Decode the transaction for modification
        decoded_tx = w0.decoderawtransaction(tx['hex'])
        print(decoded_tx)# Pretty-print the decoded transaction

        # Add the OP_CHECKGROTH16VERIFY script with the Groth16 proof
        tx_script = f"OP_CHECKGROTH16VERIFY {proof.hex()}"
        
        # Modify the vout to include the Groth16 proof in the scriptPubKey
        decoded_tx['vout'][0]['scriptPubKey']['asm'] = tx_script

        # Print the modified vout and vin
        print(f"\nvout[0] - {decoded_tx['vout'][0]}")
        print(f"\nvin[0] - {decoded_tx['vin'][0]}")
        print(f"\nvout[1] - {decoded_tx['vout'][1]}")

        # Recreate the transaction with the modified script
        modified_tx = w0.createrawtransaction([{
            'txid': decoded_tx['vin'][0]['txid'],
            'vout': decoded_tx['vin'][0]['vout'],
            'scriptSig': decoded_tx['vin'][0]['scriptSig']
        }], {address1: 1})
        
        print(f"\nmodified_tx - {modified_tx}\n")
        # Sign the modified transaction
        signed_tx = w0.signrawtransactionwithwallet(modified_tx)

        print(f"\signed_tx - {signed_tx}\n")
        # Broadcast the transaction to the network
        txid = w0.sendrawtransaction(signed_tx['hex'])

        # Verify the transaction was included in the blockchain
        tx_info = w0.gettransaction(txid)
        print(f"Transaction ID: {txid}")
        assert_equal(tx_info['confirmations'], 1)

if __name__ == '__main__':
    Groth16VerifyTest().main()