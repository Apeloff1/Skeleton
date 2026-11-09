#ifndef GAMEFORGE_H
#define GAMEFORGE_H
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef struct GfZaibatsu GfZaibatsu;
GfZaibatsu *gf_zaibatsu_create(void);
void gf_zaibatsu_destroy(GfZaibatsu *h);
void gf_free_string(char *p);
char *gf_propose(const GfZaibatsu *h,const char *ledger,const char *kind,const char *proposal_id,const char *attester,const char *value_json);
char *gf_fabric_tail(const GfZaibatsu *h,const char *ledger,uint32_t limit);
uint64_t gf_fabric_seq(const GfZaibatsu *h);
char *gf_legion_found(const GfZaibatsu *h,const char *name,const char *motto);
char *gf_legion_enlist(const GfZaibatsu *h,const char *legion,const char *capability);
char *gf_swarm_submit(const GfZaibatsu *h,const char *task_id,const char *capability,const char *payload_json,const char *deps_json);
char *gf_swarm_wave(const GfZaibatsu *h);
char *gf_governance_decide(const GfZaibatsu *h,const char *domain,const char *action,uint32_t actor_weight);
char *gf_cognition_hold(const GfZaibatsu *h,const char *predicate,bool polarity);
char *gf_cognition_testify(const GfZaibatsu *h,const char *belief_id,const char *witness,bool supports,double weight);
char *gf_lafs_put(const GfZaibatsu *h,const uint8_t *data,size_t len);
char *gf_status(const GfZaibatsu *h);
#ifdef __cplusplus
}
#endif
#endif
