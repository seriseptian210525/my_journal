flowchart TD
    %% --- Data Sources ---
    subgraph Sources [Data Ingestion]
        S1[Form Service 2024-25]
        S2[Service Unit Grab]
        S3[Form Responses]
        S4[List Request SPK]
        S5[After Repair List]
        S6[Cabang Kembangan]
        S7[Cabang Depok]
        S8[Cabang Bekasi]
        Asset[Master Asset List]
    end

    %% --- Processing Steps per Source ---
    subgraph Transform [Standardization & Enrichment]
        T1(Clean & Map Cols)
        T2(Generate Timestamps<br/>Randomized Logic)
        MergeAsset(Merge with Asset List<br/>Get VIN/Engine)
    end

    %% --- Connections Sources to Transform ---
    S1 --> T1
    S2 --> T1
    S3 --> T1
    S4 --> T1
    S5 --> T1
    S6 --> T1
    S7 --> T1
    S8 --> T1

    T1 --> MergeAsset
    Asset --> MergeAsset
    MergeAsset --> T2

    %% --- Consolidation ---
    subgraph Consolidation [Merging Data]
        Concat[Concatenate All DataFrames<br/>all_elsa_history]
    end

    T2 --> Concat

    %% --- Advanced Cleaning ---
    subgraph FinalClean [Advanced Logic Cleaning]
        FixVIN{Missing VIN?}
        LogicVIN1[Fill by Customer Mode]
        LogicVIN2[SequenceMatcher<br/>Plate Similarity]
        
        FixOdo{Odometer 0?}
        LogicOdo[Estimate Odo<br/>Time Diff * Daily Avg]
        
        FixMech[Standardize Mechanic Names<br/>Regex Matching]
        
        GenID[Generate Order ID<br/>Snowflake Methodology]
    end

    Concat --> FixVIN
    FixVIN -- Yes --> LogicVIN1
    LogicVIN1 --> LogicVIN2
    FixVIN -- No --> FixOdo
    LogicVIN2 --> FixOdo

    FixOdo -- Yes --> LogicOdo
    FixOdo -- No --> FixMech
    LogicOdo --> FixMech
    
    FixMech --> GenID

    %% --- Output ---
    subgraph Output
        FinalDB[(Final Historical DataFrame)]
        Exp[Export to CSV/GSheet]
    end

    GenID --> FinalDB
    FinalDB --> Exp