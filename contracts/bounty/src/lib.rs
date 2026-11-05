use near_sdk::collections::LookupMap;
use near_sdk::json_types::{U128, U64};
use near_sdk::{assert_one_yocto, env, near, require, AccountId, Gas, NearToken, PanicOnDefault, Promise};

const STORAGE: u128 = 10_000_000_000_000_000_000_000;
const MAX_REWARD: u128 = STORAGE;
const WEEK: u64 = 7 * 86400 * 1_000_000_000;

#[near(serializers = [borsh, json])]
#[derive(Clone, Debug, PartialEq)]
pub enum Status {
    Funded,
    Reviewed,
    PaymentPending,
    RefundPending,
    Paid,
    Refunded,
}

#[near(serializers = [borsh, json])]
#[derive(Clone)]
pub struct Bounty {
    pub id: String,
    pub maintainer: AccountId,
    pub claimant: AccountId,
    pub github_user_id: U64,
    pub repo_id: U64,
    pub issue_number: u32,
    pub terms_hash: String,
    pub amount: U128,
    pub deadline_ns: U64,
    pub delivery_hash: Option<String>,
    pub report_hash: Option<String>,
    pub status: Status,
    pub transfer_nonce: U64,
}

#[near(contract_state)]
#[derive(PanicOnDefault)]
pub struct BountyGuard {
    bounties: LookupMap<String, Bounty>,
}

fn hash(value: &str) -> bool {
    value.len() == 64 && value.bytes().all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}

fn emit(kind: &str, bounty: &Bounty) {
    env::log_str(&format!(
        "EVENT_JSON:{}",
        near_sdk::serde_json::json!({
            "standard":"bountyguard", "version":"1.0.0", "event":kind,
            "data":[{"id":bounty.id,"status":bounty.status,"claimant":bounty.claimant,
                "amount":bounty.amount,"nonce":bounty.transfer_nonce,
                "delivery_hash":bounty.delivery_hash,"report_hash":bounty.report_hash}]
        })
    ));
}

#[near]
impl BountyGuard {
    #[init]
    pub fn new() -> Self {
        require!(env::current_account_id().as_str().ends_with(".testnet"), "Testnet only");
        Self { bounties: LookupMap::new(b"b") }
    }

    /// Stores a maintainer's assigned bounty. GitHub identity is an off-chain
    /// attestation; the contract cannot independently query GitHub.
    #[payable]
    pub fn fund_assigned(
        &mut self, id: String, claimant: AccountId, github_user_id: U64,
        repo_id: U64, issue_number: u32, terms_hash: String, amount: U128,
        deadline_ns: U64,
    ) -> Bounty {
        require!(!id.is_empty() && id.len() <= 64 && id.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'-'), "Invalid bounty ID");
        require!(self.bounties.get(&id).is_none(), "Bounty already funded");
        require!(hash(&terms_hash), "Invalid terms hash");
        require!(github_user_id.0 > 0 && repo_id.0 > 0 && issue_number > 0, "Invalid GitHub reference");
        require!(amount.0 > 0 && amount.0 <= MAX_REWARD, "Development reward limit");
        require!(deadline_ns.0 > env::block_timestamp() && deadline_ns.0 - env::block_timestamp() <= WEEK, "Deadline outside seven-day window");
        require!(claimant != env::predecessor_account_id() && claimant != env::current_account_id(), "Distinct claimant required");
        require!(claimant.as_str().ends_with(".testnet"), "Named testnet claimant required");
        require!(env::attached_deposit().as_yoctonear() == amount.0.checked_add(STORAGE).expect("Amount overflow"), "Attach reward plus storage charge");
        let bounty = Bounty {
            id, maintainer: env::predecessor_account_id(), claimant, github_user_id,
            repo_id, issue_number, terms_hash, amount, deadline_ns,
            delivery_hash: None, report_hash: None, status: Status::Funded,
            transfer_nonce: U64(0),
        };
        let before = env::storage_usage();
        self.bounties.insert(&bounty.id, &bounty);
        let reserve = (env::storage_usage() - before + 200) as u128 * env::storage_byte_cost().as_yoctonear();
        require!(reserve <= STORAGE, "Storage reserve insufficient");
        emit("funded", &bounty);
        bounty
    }

    /// The maintainer commits its off-chain acceptance evidence. This is not an
    /// on-chain AI verdict or proof that the PR contains no vulnerability.
    pub fn record_review(&mut self, id: String, delivery_hash: String, report_hash: String) -> Bounty {
        let mut bounty = self.get_bounty(id).expect("Bounty missing");
        require!(env::predecessor_account_id() == bounty.maintainer, "Only maintainer");
        require!(env::block_timestamp() < bounty.deadline_ns.0, "Expired");
        require!(matches!(bounty.status, Status::Funded | Status::Reviewed), "Not reviewable");
        require!(hash(&delivery_hash) && hash(&report_hash), "Invalid evidence hash");
        bounty.delivery_hash = Some(delivery_hash);
        bounty.report_hash = Some(report_hash);
        bounty.status = Status::Reviewed;
        self.bounties.insert(&bounty.id, &bounty);
        emit("review_recorded", &bounty);
        bounty
    }

    #[payable]
    pub fn pay(&mut self, id: String, expected_delivery_hash: String, expected_report_hash: String) -> Promise {
        assert_one_yocto();
        let mut bounty = self.get_bounty(id).expect("Bounty missing");
        require!(env::predecessor_account_id() == bounty.maintainer, "Only maintainer");
        require!(bounty.status == Status::Reviewed, "No payable review");
        require!(env::block_timestamp() < bounty.deadline_ns.0, "Expired");
        require!(bounty.delivery_hash.as_deref() == Some(expected_delivery_hash.as_str()), "Delivery changed");
        require!(bounty.report_hash.as_deref() == Some(expected_report_hash.as_str()), "Review changed");
        require!(env::prepaid_gas() >= Gas::from_tgas(40), "Insufficient callback gas");
        bounty.status = Status::PaymentPending;
        bounty.transfer_nonce.0 = bounty.transfer_nonce.0.checked_add(1).expect("Nonce overflow");
        self.bounties.insert(&bounty.id, &bounty);
        emit("payment_pending", &bounty);
        self.transfer(&bounty, bounty.claimant.clone())
    }

    /// Any caller/keeper may trigger expiry. Only reward principal is refunded.
    pub fn refund_expired(&mut self, id: String) -> Promise {
        let mut bounty = self.get_bounty(id).expect("Bounty missing");
        require!(env::block_timestamp() >= bounty.deadline_ns.0, "Not expired");
        require!(matches!(bounty.status, Status::Funded | Status::Reviewed), "Not refundable");
        require!(env::prepaid_gas() >= Gas::from_tgas(40), "Insufficient callback gas");
        bounty.status = Status::RefundPending;
        bounty.transfer_nonce.0 = bounty.transfer_nonce.0.checked_add(1).expect("Nonce overflow");
        self.bounties.insert(&bounty.id, &bounty);
        emit("refund_pending", &bounty);
        self.transfer(&bounty, bounty.maintainer.clone())
    }

    #[private]
    pub fn finish_transfer(&mut self, id: String, nonce: U64) -> bool {
        require!(env::predecessor_account_id() == env::current_account_id(), "Runtime callback only");
        require!(env::promise_results_count() == 1, "One transfer result required");
        let mut bounty = self.get_bounty(id).expect("Bounty missing");
        require!(bounty.transfer_nonce == nonce, "Stale callback");
        require!(matches!(bounty.status, Status::PaymentPending | Status::RefundPending), "No pending transfer");
        let success = env::promise_result_checked(0, 1024).is_ok();
        bounty.status = match (&bounty.status, success) {
            (Status::PaymentPending, true) => Status::Paid,
            (Status::RefundPending, true) => Status::Refunded,
            (_, false) if bounty.delivery_hash.is_some() => Status::Reviewed,
            (_, false) => Status::Funded,
            _ => unreachable!(),
        };
        self.bounties.insert(&bounty.id, &bounty);
        emit(if success { "transfer_completed" } else { "transfer_failed" }, &bounty);
        success
    }

    pub fn get_bounty(&self, id: String) -> Option<Bounty> { self.bounties.get(&id) }
    pub fn storage_charge(&self) -> U128 { U128(STORAGE) }
}

impl BountyGuard {
    fn transfer(&self, bounty: &Bounty, receiver: AccountId) -> Promise {
        Promise::new(receiver).transfer(NearToken::from_yoctonear(bounty.amount.0)).then(
            Self::ext(env::current_account_id()).with_static_gas(Gas::from_tgas(15))
                .finish_transfer(bounty.id.clone(), bounty.transfer_nonce),
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use near_sdk::test_utils::VMContextBuilder;
    use near_sdk::{testing_env, PromiseResult};

    fn context(who: &str, deposit: u128, time: u64) {
        testing_env!(VMContextBuilder::new()
            .current_account_id("bounties.testnet".parse().unwrap())
            .predecessor_account_id(who.parse().unwrap())
            .signer_account_id(who.parse().unwrap())
            .attached_deposit(NearToken::from_yoctonear(deposit))
            .prepaid_gas(Gas::from_tgas(100)).block_timestamp(time).build());
    }
    fn funded() -> BountyGuard {
        context("owner.testnet", STORAGE + 100, 1);
        let mut contract = BountyGuard::new();
        contract.fund_assigned("one".into(), "worker.testnet".parse().unwrap(), U64(9), U64(42), 12, "a".repeat(64), U128(100), U64(1000));
        contract
    }
    fn reviewed() -> BountyGuard {
        let mut contract = funded();
        context("owner.testnet", 0, 2);
        contract.record_review("one".into(), "b".repeat(64), "c".repeat(64));
        contract
    }
    fn result(success: bool) {
        let ctx = VMContextBuilder::new().current_account_id("bounties.testnet".parse().unwrap())
            .predecessor_account_id("bounties.testnet".parse().unwrap()).build();
        testing_env!(ctx, near_sdk::test_vm_config(), near_sdk::RuntimeFeesConfig::test(), Default::default(), vec![if success { PromiseResult::Successful(vec![]) } else { PromiseResult::Failed }]);
    }
    #[test]
    fn identity_and_terms_are_immutable() {
        let contract = funded(); let bounty = contract.get_bounty("one".into()).unwrap();
        assert_eq!(bounty.github_user_id.0, 9); assert_eq!(bounty.repo_id.0, 42);
        assert_eq!(bounty.claimant.as_str(), "worker.testnet"); assert_eq!(bounty.terms_hash, "a".repeat(64));
    }
    #[test]
    fn payment_only_completes_in_callback() {
        let mut contract = reviewed(); context("owner.testnet", 1, 3);
        let _ = contract.pay("one".into(), "b".repeat(64), "c".repeat(64));
        assert_eq!(contract.get_bounty("one".into()).unwrap().status, Status::PaymentPending);
        result(true); assert!(contract.finish_transfer("one".into(), U64(1)));
        assert_eq!(contract.get_bounty("one".into()).unwrap().status, Status::Paid);
    }
    #[test]
    fn failed_payment_restores_review() {
        let mut contract = reviewed(); context("owner.testnet", 1, 3);
        let _ = contract.pay("one".into(), "b".repeat(64), "c".repeat(64));
        result(false); assert!(!contract.finish_transfer("one".into(), U64(1)));
        assert_eq!(contract.get_bounty("one".into()).unwrap().status, Status::Reviewed);
        context("owner.testnet", 1, 4); let _ = contract.pay("one".into(), "b".repeat(64), "c".repeat(64));
        result(true); assert!(contract.finish_transfer("one".into(), U64(2)));
    }
    #[test]
    fn expiry_refunds_original_maintainer() {
        let mut contract = funded(); context("keeper.testnet", 0, 1000);
        let _ = contract.refund_expired("one".into()); result(true);
        assert!(contract.finish_transfer("one".into(), U64(1)));
        assert_eq!(contract.get_bounty("one".into()).unwrap().status, Status::Refunded);
    }
    #[test]
    #[should_panic(expected = "Delivery changed")]
    fn old_delivery_cannot_be_paid() {
        let mut contract = reviewed(); context("owner.testnet", 1, 3);
        let _ = contract.pay("one".into(), "d".repeat(64), "c".repeat(64));
    }
    #[test]
    #[should_panic(expected = "Review changed")]
    fn old_report_cannot_be_paid() {
        let mut contract = reviewed(); context("owner.testnet", 1, 3);
        let _ = contract.pay("one".into(), "b".repeat(64), "d".repeat(64));
    }
    #[test]
    #[should_panic(expected = "Only maintainer")]
    fn claimant_cannot_approve_itself() {
        let mut contract = reviewed(); context("worker.testnet", 1, 3);
        let _ = contract.pay("one".into(), "b".repeat(64), "c".repeat(64));
    }
    #[test]
    #[should_panic(expected = "No payable review")]
    fn no_double_payment() {
        let mut contract = reviewed(); context("owner.testnet", 1, 3);
        let _ = contract.pay("one".into(), "b".repeat(64), "c".repeat(64));
        result(true); contract.finish_transfer("one".into(), U64(1));
        context("owner.testnet", 1, 4); let _ = contract.pay("one".into(), "b".repeat(64), "c".repeat(64));
    }
    #[test]
    #[should_panic(expected = "Stale callback")]
    fn stale_callback_cannot_finalize_retry() {
        let mut contract = reviewed(); context("owner.testnet", 1, 3);
        let _ = contract.pay("one".into(), "b".repeat(64), "c".repeat(64)); result(false);
        contract.finish_transfer("one".into(), U64(1)); context("owner.testnet", 1, 4);
        let _ = contract.pay("one".into(), "b".repeat(64), "c".repeat(64)); result(true);
        contract.finish_transfer("one".into(), U64(1));
    }
}
