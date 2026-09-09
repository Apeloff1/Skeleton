    def ask(self, session_id: str, input_text: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        session = self._memory.get_session(session_id)
        if not session:
            return {"error": "Session not found", "session_id": session_id}

        session.add_turn("user", input_text, **(context or {}))

        # Matrices observe the input
        self.sam.observe(input_text)
        for term in self.sam._terms(input_text):
            self.krem.observe(term)

        # SAM expansion enriches the prompt with associated concepts
        expansions = self.sam.expand(input_text)
        system = MODE_SYSTEM_PROMPTS.get(session.mode, "")
        prompt = f"{system}\n\n{input_text}" if system else input_text
        if expansions:
            prompt += f"\n\nRelated concepts: {', '.join(expansions[:5])}"

        # Citations: graph facts supporting this query (+ SAM context)
        cited = self.citations.cite(input_text, context_terms=expansions)
        if cited:
            prompt += "\n\nKnown facts:\n" + "\n".join(f"- {c.render()}" for c in cited[:5])

        start = time.time()
        try:
            content = self._provider.complete(prompt, context=session.context_window())
            success = True
        except Exception as e:
            content = f"[provider error: {e}]"
            success = False
        latency_ms = (time.time() - start) * 1000

        # CLOM tracks the outcome for this intent (= session mode)
        self.clom.observe(session.mode.value, success, latency_ms)

        # Matrices observe the response too (assistant language feeds SAM)
        self.sam.observe(content)

        tools_used = [t for t in self._tools if t in input_text.lower()]
        for tool in tools_used:
            try:
                self._tools[tool]({"input": input_text, "session": session.to_dict()})
                self._stats["tool_calls"] += 1
            except Exception:
                pass

        # Context fabric: consume the interjection earned last turn, then
        # run the between-turns cycle on this reply (distill → execute → guide)
        cycle_report = None
        interjection = None
        if self._cycle is not None:
            interjection = self._cycle.before_reply()
            if interjection:
                content = interjection + "\n\n" + content
            token_count = max(1, len(content) // 4)  # rough token estimate
            cycle_report = self._cycle.after_reply(content, token_count)

        session.add_turn("assistant", content, tools_used=tools_used,
                         provider=self.provider_name, citations=len(cited))
        self._stats["interactions"] += 1

        if self._bus:
            self._bus.emit("jeeves.interaction", {
                "session_id": session_id,
                "provider": self.provider_name,
                "input_length": len(input_text),
                "response_length": len(content),
                "sam_expansions": len(expansions),
                "citations": len(cited),
                "latency_ms": latency_ms,
            })

        result: Dict[str, Any] = {
            "content": content,
            "tools": tools_used,
            "mode": session.mode.value,
            "provider": self.provider_name,
            "expansions": expansions[:5],
            "citations": [c.to_dict() for c in cited],
            "latency_ms": round(latency_ms, 1),
        }
        if interjection:
            result["interjection"] = interjection
        if cycle_report is not None:
            result["cycle"] = cycle_report.to_dict()
            if cycle_report.oracle_shift:
                result["oracle"] = cycle_report.oracle_shift
        return result
