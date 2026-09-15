package gfclient

import("bytes";"encoding/json";"fmt";"io";"net/http";"time")
type Client struct{Base string;Seal string;http *http.Client}
func New(base string)*Client{return &Client{Base:base,http:&http.Client{Timeout:10*time.Second}}}
func(c *Client)WithSeal(seal string)*Client{c.Seal=seal;return c}
func(c *Client)call(method,path string,body,out any)error{var rdr io.Reader;if body!=nil{b,err:=json.Marshal(body);if err!=nil{return err};rdr=bytes.NewReader(b)};req,err:=http.NewRequest(method,c.Base+path,rdr);if err!=nil{return err};req.Header.Set("Content-Type","application/json");if c.Seal!=""{req.Header.Set("x-gf-seal",c.Seal)};resp,err:=c.http.Do(req);if err!=nil{return err};defer resp.Body.Close();data,err:=io.ReadAll(io.LimitReader(resp.Body,1<<22));if err!=nil{return err};if resp.StatusCode>=400{return fmt.Errorf("gf-server %s %s: %d: %s",method,path,resp.StatusCode,data)};if out!=nil{return json.Unmarshal(data,out)};return nil}
type ProposeResponse struct{Verdict string `json:"verdict"`;EventID string `json:"event_id,omitempty"`;Seq uint64 `json:"seq,omitempty"`}
func(c *Client)Propose(ledger,kind,proposalID string,value any)(*ProposeResponse,error){out:=&ProposeResponse{};err:=c.call("POST","/api/fabric/propose",map[string]any{"ledger":ledger,"kind":kind,"proposal_id":proposalID,"value":value},out);return out,err}
func(c *Client)FabricTail(ledger string)([]map[string]any,error){var out []map[string]any;err:=c.call("GET","/api/fabric/"+ledger+"/tail",nil,&out);return out,err}
type Decision struct{Permitted bool `json:"permitted"`;CitedRule string `json:"cited_rule,omitempty"`;Reason string `json:"reason"`}
func(c *Client)Decide(domain,action string,actorWeight uint32)(*Decision,error){out:=&Decision{};err:=c.call("POST","/api/governance/decide",map[string]any{"domain":domain,"action":action,"actor_weight":actorWeight},out);return out,err}
func(c *Client)SubmitTask(id,capability string,payload any,deps []string)error{return c.call("POST","/api/swarm/submit",map[string]any{"id":id,"capability":capability,"payload":payload,"deps":deps},nil)}
func(c *Client)ReadyWave()([]map[string]any,error){var out []map[string]any;err:=c.call("GET","/api/swarm/wave",nil,&out);return out,err}
func(c *Client)Infra()(map[string]any,error){var out map[string]any;err:=c.call("GET","/api/infra",nil,&out);return out,err}
func(c *Client)Health()(bool,error){var out struct{Status string `json:"status"`};err:=c.call("GET","/health",nil,&out);return out.Status=="ok",err}
