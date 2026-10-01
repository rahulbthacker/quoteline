<!-- version: line_matcher_v1
     purpose: Break a tie when a vendor's row could match more than one RFx line. -->

A vendor's quoted row has to be matched to one line of the buyer's RFx. A deterministic
scorer compared the specifications (dimensions, ply, GSM, print, item wording) and could not
choose between the candidates shown.

Pick the RFx line the vendor's row refers to, or say that none of the candidates is a real
match. Judge only from the item itself: its type, dimensions, ply, GSM and printing. Ignore
price. A vendor's own serial number is not the buyer's line number unless the document says
so. If two candidates fit equally well, choose `none`: a wrong match is worse than a flagged
row.

Give a one-sentence `reason` a buyer could check against the documents.
