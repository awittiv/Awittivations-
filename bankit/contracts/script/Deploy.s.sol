// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Script.sol";
import "../src/BankitStablecoin.sol";
import "../src/BankitLiquidityRouter.sol";

/// @notice Deploy BankitStablecoin + BankitLiquidityRouter to Polygon Amoy.
///
/// Usage:
///   forge script script/Deploy.s.sol:Deploy \
///     --rpc-url amoy \
///     --broadcast \
///     --verify \
///     -vvvv
///
/// Required env vars:
///   ORACLE_PRIVATE_KEY  — deployer / oracle wallet private key
///   POLYGONSCAN_API_KEY — for contract verification
contract Deploy is Script {
    function run() external {
        uint256 deployerKey = vm.envUint("ORACLE_PRIVATE_KEY");
        address deployer = vm.addr(deployerKey);

        console2.log("Deploying from:", deployer);

        vm.startBroadcast(deployerKey);

        BankitStablecoin stablecoin = new BankitStablecoin(deployer);
        console2.log("BankitStablecoin (BKD):", address(stablecoin));

        BankitLiquidityRouter router = new BankitLiquidityRouter(
            address(stablecoin),
            deployer
        );
        console2.log("BankitLiquidityRouter:  ", address(router));

        stablecoin.grantRole(stablecoin.ROUTER_ROLE(), address(router));
        console2.log("Granted ROUTER_ROLE to router on stablecoin");

        vm.stopBroadcast();

        console2.log("");
        console2.log("=== Update .env ===");
        console2.log("CONTRACT_ADDRESS=", address(router));
        console2.log("STABLECOIN_ADDRESS=", address(stablecoin));
    }
}
