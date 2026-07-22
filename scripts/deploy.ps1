[CmdletBinding()]
param(
    [string] $ProjectId = "nyc-taxi-analytics-503113",
    [string] $ProjectNumber = "411442366180",
    [string] $Region = "us-central1"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$GcloudCommand = Get-Command gcloud -ErrorAction SilentlyContinue
if ($GcloudCommand) {
    $Gcloud = $GcloudCommand.Source
}
else {
    $Gcloud = Join-Path $env:LOCALAPPDATA `
        "Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"
    if (-not (Test-Path -LiteralPath $Gcloud)) {
        throw "gcloud is required"
    }
}

function Invoke-Gcloud {
    param([Parameter(Mandatory = $true)][string[]] $Arguments)

    & $Gcloud @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "gcloud failed: $($Arguments -join ' ')"
    }
}

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Push-Location $RepoRoot

try {
    $Branch = (& git branch --show-current).Trim()
    if ($LASTEXITCODE -ne 0 -or $Branch -ne "main") {
        throw "deployment must run from the main branch"
    }
    if (& git status --porcelain) {
        throw "commit or remove local changes before deployment"
    }

    $Commit = (& git rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "could not resolve the current commit"
    }

    $JobName = "nyc-taxi-pipeline"
    $SchedulerName = "nyc-taxi-daily"
    $BuildBucket = "$ProjectId-build-$ProjectNumber"
    $BuildServiceAccount = "nyc-taxi-build@$ProjectId.iam.gserviceaccount.com"
    $RuntimeServiceAccount = "nyc-taxi-pipeline@$ProjectId.iam.gserviceaccount.com"
    $SchedulerServiceAccount = "nyc-taxi-scheduler@$ProjectId.iam.gserviceaccount.com"
    $Image = "${Region}-docker.pkg.dev/${ProjectId}/nyc-taxi/pipeline:${Commit}"
    $RunUri = "https://run.googleapis.com/v2/projects/$ProjectId/locations/$Region/jobs/${JobName}:run"

    Invoke-Gcloud -Arguments @(
        "builds", "submit", ".",
        "--project=$ProjectId",
        "--region=$Region",
        "--config=cloudbuild.yaml",
        "--service-account=projects/$ProjectId/serviceAccounts/$BuildServiceAccount",
        "--gcs-source-staging-dir=gs://$BuildBucket/source",
        "--substitutions=_IMAGE=$Image"
    )

    $SchedulerState = (Invoke-Gcloud -Arguments @(
        "scheduler", "jobs", "describe", $SchedulerName,
        "--project=$ProjectId", "--location=$Region",
        "--format=value(state)"
    )).Trim()

    if ($SchedulerState -eq "ENABLED") {
        Invoke-Gcloud -Arguments @(
            "scheduler", "jobs", "pause", $SchedulerName,
            "--project=$ProjectId", "--location=$Region", "--quiet"
        )
    }
    elseif ($SchedulerState -ne "PAUSED") {
        throw "unexpected scheduler state: $SchedulerState"
    }

    Invoke-Gcloud -Arguments @(
        "run", "jobs", "deploy", $JobName,
        "--project=$ProjectId", "--region=$Region",
        "--image=$Image",
        "--service-account=$RuntimeServiceAccount",
        "--cpu=1", "--memory=512Mi", "--tasks=1",
        "--max-retries=1", "--task-timeout=60m",
        "--set-env-vars=GCP_PROJECT_ID=$ProjectId,GCP_PROJECT_NUMBER=$ProjectNumber,GCP_LOCATION=$Region",
        "--args=discover,--lookback-months,3", "--quiet"
    )

    Invoke-Gcloud -Arguments @(
        "run", "jobs", "execute", $JobName,
        "--project=$ProjectId", "--region=$Region", "--wait"
    )

    Invoke-Gcloud -Arguments @(
        "scheduler", "jobs", "update", "http", $SchedulerName,
        "--project=$ProjectId", "--location=$Region",
        "--schedule=0 6 * * *", "--time-zone=America/New_York",
        "--uri=$RunUri", "--http-method=POST",
        "--oauth-service-account-email=$SchedulerServiceAccount", "--quiet"
    )

    $SchedulerState = (Invoke-Gcloud -Arguments @(
        "scheduler", "jobs", "describe", $SchedulerName,
        "--project=$ProjectId", "--location=$Region",
        "--format=value(state)"
    )).Trim()
    if ($SchedulerState -eq "PAUSED") {
        Invoke-Gcloud -Arguments @(
            "scheduler", "jobs", "resume", $SchedulerName,
            "--project=$ProjectId", "--location=$Region", "--quiet"
        )
    }
    elseif ($SchedulerState -ne "ENABLED") {
        throw "unexpected scheduler state after update: $SchedulerState"
    }

    Invoke-Gcloud -Arguments @(
        "run", "jobs", "describe", $JobName,
        "--project=$ProjectId", "--region=$Region",
        "--format=yaml(spec.template.spec.template.spec.containers[0].image,spec.template.spec.template.spec.containers[0].args,spec.template.spec.template.spec.containers[0].resources.limits,spec.template.spec.template.spec.serviceAccountName,status.latestCreatedExecution)"
    )
    Invoke-Gcloud -Arguments @(
        "scheduler", "jobs", "describe", $SchedulerName,
        "--project=$ProjectId", "--location=$Region",
        "--format=yaml(state,schedule,timeZone,httpTarget.uri,httpTarget.oauthToken.serviceAccountEmail)"
    )
}
finally {
    Pop-Location
}
