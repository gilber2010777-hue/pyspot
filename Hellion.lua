local UIS = game:GetService("UserInputService")
local Debris = game:GetService("Debris")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local HapticService = game:GetService("HapticService")
local ContentProvider = game:GetService("ContentProvider")

local player = game.Players.LocalPlayer
local camera = workspace.CurrentCamera
local character = player.Character or player.CharacterAdded:Wait()
local humanoid = character:WaitForChild("Humanoid")
local animator = humanoid:WaitForChild("Animator")

local DanoZumbiEvent = ReplicatedStorage:WaitForChild("DanoZumbi")
local ConfigurarGrip = ReplicatedStorage:WaitForChild("ConfigurarGrip")
local ParticulasTiroEvent = ReplicatedStorage:WaitForChild("ParticulasTiro")
local InclinacaoBracoEvent = ReplicatedStorage:WaitForChild("InclinacaoBracominigun")
local SomArmaEvent = ReplicatedStorage:WaitForChild("SomArmaEvent")

local tool = script.Parent
local animFolder = tool:WaitForChild("Animations")
local handle = tool:WaitForChild("Handle")
local balaTemplate = tool:WaitForChild("BALA")
local canoArma = nil

local IMPACTO_VISUAL = {
	IntensidadeZoom = 4,      
	VelocidadeRetorno = 0.15, 
	TamanhoImpacto = 0.4,     
}

local LIMITES = {
	MaxSubir = 90,
	MaxDescer = 90,
	LimitarCamera = true
}

local originalFOV = camera.FieldOfView

local originalRightC0, originalLeftC0, originalNeckC0 = nil, nil, nil

local thetaAtivo = 0
local VELOCIDADE_TRANSICAO_RECARGA = 8
local VELOCIDADE_RETORNO_MIRA = 12
local isTransicaoRecarga = false

local mouseDestrancado = false
local podeAtirar = false

local GRIP_C0 = CFrame.new(-0.417, -0.876, -0.355) * CFrame.Angles(math.rad(-90), 0, 0)
local GRIP_C1 = CFrame.new(0.029, 0.636, -0.032)

local rayParams = RaycastParams.new()
rayParams.FilterType = Enum.RaycastFilterType.Exclude

local diedConn = nil

for _, obj in ipairs(tool:GetDescendants()) do
	if obj.Name == "Cylinder.008" and obj:IsA("BasePart") then
		canoArma = obj
		break
	end
end

for _, obj in ipairs(tool:GetDescendants()) do
	if obj:IsA("BasePart") and obj.Name:match("N$") then
		obj.Transparency = 1
	end
end

local EfeitosParticulas = require(ReplicatedStorage:WaitForChild("EfeitosParticulas"))
local AmmoUIManager = require(ReplicatedStorage:WaitForChild("AmmoUIManager"))
local particleEmitters, beamsEfeito = nil, nil
local animIdle = animFolder:WaitForChild("Animation")
local animShoot = animFolder:WaitForChild("Animation1")
local animReload = animFolder:WaitForChild("Animation3")


task.spawn(function()
	pcall(function()
		ContentProvider:PreloadAsync({tool, animIdle, animShoot, animReload})
	end)
end)

local idleTrack, shootTrack, reloadTrack
local isEquipped = false
local isMouseDown = false
local ammo = 1500         
local maxAmmo = 1500    
local fireRate = 0.1
local isReloading = false 
local reloadTime = 2.5    
local reserveAmmo = 3000
local maxReserveAmmo = 3000

local rightShoulder, leftShoulder, neck = nil, nil, nil

local function setupTrack(animObject, priority, isLoop)
	if not animator then return end 
	local track = animator:LoadAnimation(animObject)
	track.Priority = priority
	track.Looped = isLoop
	return track
end

local function stopAllTracks()
	if idleTrack then pcall(function() idleTrack:Stop(0) end) end
	if shootTrack then pcall(function() shootTrack:Stop(0) end) end
	if reloadTrack then pcall(function() reloadTrack:Stop(0) end) end
end

local function destroyAllTracks()
	if idleTrack then pcall(function() idleTrack:Destroy() end) end
	if shootTrack then pcall(function() shootTrack:Destroy() end) end
	if reloadTrack then pcall(function() reloadTrack:Destroy() end) end
	idleTrack = nil
	shootTrack = nil
	reloadTrack = nil
end

local function loadAnims()
	stopAllTracks()
	destroyAllTracks()
	idleTrack = setupTrack(animIdle, Enum.AnimationPriority.Movement, true)
	shootTrack = setupTrack(animShoot, Enum.AnimationPriority.Action, false)
	reloadTrack = setupTrack(animReload, Enum.AnimationPriority.Action, false)
end

local updateConnection = nil

local function solicitarMotor6D()
	local rightArm = character:FindFirstChild("Right Arm") or character:FindFirstChild("RightHand")
	if rightArm then
		local grip = rightArm:FindFirstChild("RightGrip")
		if grip then grip:Destroy() end

		local staleHolder = rightArm:FindFirstChild("Holder")
		if staleHolder then staleHolder:Destroy() end


		local antigoM6D = rightArm:FindFirstChild("ToolGrip6D")
		if antigoM6D and antigoM6D.Part1 == handle then 
			antigoM6D:Destroy() 
		end

		local m6d = Instance.new("Motor6D")
		m6d.Name = "ToolGrip6D"
		m6d.Part0 = rightArm
		m6d.Part1 = handle
		m6d.C0 = GRIP_C0
		m6d.C1 = GRIP_C1
		m6d.Parent = rightArm
	end

	local torso = character:FindFirstChild("Torso") or character:FindFirstChild("UpperTorso")
	local mochilaHandle = tool:FindFirstChild("BackpackHandle")

	if torso and mochilaHandle then
		local oldMochilaGrip = torso:FindFirstChild("MochilaGrip6D")
		if oldMochilaGrip then oldMochilaGrip:Destroy() end

		local m6dMochila = Instance.new("Motor6D")
		m6dMochila.Name = "MochilaGrip6D"
		m6dMochila.Part0 = torso
		m6dMochila.Part1 = mochilaHandle

		m6dMochila.C0 = CFrame.new(0.158, 0.082, 0.245) 
		m6dMochila.C1 = CFrame.new(0, 0, 0)
		m6dMochila.Parent = torso
	end

	ConfigurarGrip:FireServer(tool, handle, mochilaHandle)

	if torso then
		rightShoulder = torso:FindFirstChild("Right Shoulder") or (character:FindFirstChild("RightUpperArm") and character.RightUpperArm:FindFirstChild("RightShoulder"))
		leftShoulder = torso:FindFirstChild("Left Shoulder") or (character:FindFirstChild("LeftUpperArm") and character.LeftUpperArm:FindFirstChild("LeftShoulder"))
	end

	local head = character:FindFirstChild("Head")
	if head then
		neck = head:FindFirstChild("Neck") or (torso and torso:FindFirstChild("Neck"))
	end


	local rigType = humanoid and humanoid.RigType
	if rigType == Enum.HumanoidRigType.R6 then
		originalRightC0 = CFrame.new(1, 0.5, 0) * CFrame.Angles(0, math.pi/2, 0)
		originalLeftC0 = CFrame.new(-1, 0.5, 0) * CFrame.Angles(0, -math.pi/2, 0)
		originalNeckC0 = CFrame.new(0, 1, 0) * CFrame.Angles(-math.pi/2, 0, math.pi)
	else
		originalRightC0 = CFrame.new(1, 0.5, 0)
		originalLeftC0 = CFrame.new(-1, 0.5, 0)
		originalNeckC0 = CFrame.new(0, 1, 0)
	end

	if updateConnection then updateConnection:Disconnect() end
	updateConnection = RunService.RenderStepped:Connect(function(dt)
		if not isEquipped or not character or humanoid.Health <= 0 then return end

		if mouseDestrancado then
			UIS.MouseBehavior = Enum.MouseBehavior.Default
			return 
		else
			UIS.MouseBehavior = Enum.MouseBehavior.LockCenter
		end

		camera.FieldOfView = math.lerp(camera.FieldOfView, originalFOV, IMPACTO_VISUAL.VelocidadeRetorno)

		local rightArm = character:FindFirstChild("Right Arm") or character:FindFirstChild("RightHand")
		if rightArm then
			local m = rightArm:FindFirstChild("ToolGrip6D")

			if m and m.Part1 == handle then
				m.C0 = GRIP_C0
				m.C1 = GRIP_C1
			end
		end

		local cameraCFrame = camera.CFrame
		local theta = math.asin(cameraCFrame.LookVector.Y)
		local minRad = math.rad(-LIMITES.MaxDescer)
		local maxRad = math.rad(LIMITES.MaxSubir)
		local thetaLimitado = math.clamp(theta, minRad, maxRad)

		if LIMITES.LimitarCamera then
			local yaw = math.atan2(-cameraCFrame.LookVector.X, -cameraCFrame.LookVector.Z)
			if theta > maxRad then
				camera.CFrame = CFrame.new(cameraCFrame.Position) * CFrame.Angles(0, yaw, 0) * CFrame.Angles(maxRad, 0, 0)
			elseif theta < minRad then
				camera.CFrame = CFrame.new(cameraCFrame.Position) * CFrame.Angles(0, yaw, 0) * CFrame.Angles(minRad, 0, 0)
			end
		end

		local thetaFinal = thetaLimitado

		if isReloading or isTransicaoRecarga then
			if isReloading and not isTransicaoRecarga then
				isTransicaoRecarga = true
			end

			local thetaAlvo = isReloading and 0 or thetaLimitado
			local velocidade = isReloading and VELOCIDADE_TRANSICAO_RECARGA or VELOCIDADE_RETORNO_MIRA
			local fatorLerp = 1 - math.exp(-velocidade * dt)
			thetaAtivo = thetaAtivo + (thetaAlvo - thetaAtivo) * fatorLerp

			if not isReloading and math.abs(thetaAtivo - thetaLimitado) < 0.005 then
				isTransicaoRecarga = false
				thetaAtivo = thetaLimitado
			end

			thetaFinal = thetaAtivo
		else
			thetaAtivo = thetaLimitado
		end

		InclinacaoBracoEvent:FireServer(thetaFinal)

		if humanoid.RigType == Enum.HumanoidRigType.R6 then
			if rightShoulder and originalRightC0 then
				rightShoulder.C0 = originalRightC0 * CFrame.Angles(0, 0, thetaFinal)
			end
			if leftShoulder and originalLeftC0 then
				leftShoulder.C0 = originalLeftC0 * CFrame.Angles(0, 0, -thetaFinal)
			end
			if neck and originalNeckC0 then
				neck.C0 = originalNeckC0 * CFrame.Angles(-thetaFinal, 0, 0)
			end
		else
			if rightShoulder and originalRightC0 then
				rightShoulder.C0 = originalRightC0 * CFrame.Angles(-thetaFinal, 0, 0)
			end
			if leftShoulder and originalLeftC0 then
				leftShoulder.C0 = originalLeftC0 * CFrame.Angles(-thetaFinal, 0, 0)
			end
			if neck and originalNeckC0 then
				neck.C0 = originalNeckC0 * CFrame.Angles(-thetaFinal, 0, 0)
			end
		end
	end)
end

local function atirar()
	if not podeAtirar or ammo <= 0 or mouseDestrancado or not isEquipped then if ammo <= 0 then pcall(function() AmmoUIManager.shakeAmmoUI() end) end return end
	ammo -= 1
	pcall(function() AmmoUIManager.updateAmmoUI(ammo, maxAmmo, reserveAmmo, maxReserveAmmo) end)
	if shootTrack then shootTrack:Play() end

	local pontoSaida = canoArma or handle
	camera.FieldOfView = originalFOV - IMPACTO_VISUAL.IntensidadeZoom

	local origem = pontoSaida.Position
	local direcao = camera.CFrame.LookVector 
	local alcanceMaximo = 1000
	local destino = origem + (direcao * alcanceMaximo)

	local novaBala = balaTemplate:Clone()
	novaBala.Parent = workspace
	novaBala.CFrame = CFrame.lookAt(origem, origem + direcao)
	novaBala.CanCollide = false
	novaBala.AssemblyLinearVelocity = direcao * 400
	Debris:AddItem(novaBala, 1.5)

	rayParams.FilterDescendantsInstances = {character, tool, novaBala}

	local resultado = workspace:Spherecast(origem, 0.6, direcao * alcanceMaximo, rayParams)

	if resultado and resultado.Instance then
		local hit = resultado.Instance
		destino = resultado.Position

		if not (hit.Name:lower():find("beam") or hit.Name:lower():find("light") or hit.Transparency > 0.8) then
			local model = hit:FindFirstAncestorOfClass("Model")
			if model and model:FindFirstChild("Humanoid") then
				DanoZumbiEvent:FireServer(model, hit.Name, resultado.Position)
			end
			novaBala.Position = resultado.Position
			novaBala.AssemblyLinearVelocity = Vector3.zero
			Debris:AddItem(novaBala, 0.05)
		end
	end
	local direcaoArma = (canoArma or handle).CFrame
	EfeitosParticulas.Disparar(particleEmitters, beamsEfeito, destino, direcaoArma)
	ParticulasTiroEvent:FireServer(tool.Name, destino, direcaoArma)
end

local function recarregar()
	if isReloading or mouseDestrancado or not isEquipped then return end
	if ammo >= maxAmmo then return end
	if reserveAmmo <= 0 then return end
	isReloading = true
	isMouseDown = false

	pcall(function()
		if HapticService:IsVibrationSupported(Enum.UserInputType.Gamepad1) then
			HapticService:SetMotor(Enum.UserInputType.Gamepad1, Enum.VibrationMotor.Small, 0.75)
			task.delay(0.3, function()
				HapticService:SetMotor(Enum.UserInputType.Gamepad1, Enum.VibrationMotor.Small, 0)
			end)
		end
	end)

	if reloadTrack then
		reloadTrack:Play()
		local reloadDone = false
		local endedConn
		endedConn = reloadTrack.Ended:Connect(function()
			reloadDone = true
		end)
		local tempoEspera = 0
		while not reloadDone and tempoEspera < (reloadTime + 2) do
			task.wait(0.05)
			tempoEspera += 0.05
		end
		if endedConn then endedConn:Disconnect() end
		pcall(function() reloadTrack:Stop(0.2) end)
	else
		task.wait(reloadTime) 
	end
	if not isEquipped then return end
	local needed = maxAmmo - ammo
	local toTake = math.min(needed, reserveAmmo)
	ammo = ammo + toTake
	reserveAmmo = reserveAmmo - toTake
	isReloading = false
	pcall(function() AmmoUIManager.reloadAmmoUI(ammo, maxAmmo, reserveAmmo, maxReserveAmmo) end)
	if idleTrack and isEquipped then
		idleTrack:AdjustWeight(1, 0.2)  
	end
end

local tiroAtivo = false

local function loopTiro()
	if tiroAtivo then return end
	tiroAtivo = true
	while isMouseDown and isEquipped and ammo > 0 and not isReloading and not mouseDestrancado do
		atirar()
		local waitedUntil = tick() + fireRate
		repeat 
			task.wait(0.03) 
		until tick() >= waitedUntil or not isMouseDown or not isEquipped

		if not isMouseDown or mouseDestrancado or not isEquipped then break end
	end
	tiroAtivo = false
	if ammo <= 0 and not isReloading and isEquipped and not mouseDestrancado then
		task.spawn(recarregar)
	end
end

UIS.InputBegan:Connect(function(input, gpe)
	if gpe or not isEquipped then return end

	if input.KeyCode == Enum.KeyCode.P or input.KeyCode == Enum.KeyCode.ButtonY then
		mouseDestrancado = not mouseDestrancado
		if mouseDestrancado then
			isMouseDown = false 
			UIS.MouseBehavior = Enum.MouseBehavior.Default
		else
			UIS.MouseBehavior = Enum.MouseBehavior.LockCenter
		end
		return
	end

	if input.KeyCode == Enum.KeyCode.R or input.KeyCode == Enum.KeyCode.ButtonB then
		if mouseDestrancado then return end
		task.spawn(recarregar)
		return
	end

	if input.UserInputType == Enum.UserInputType.MouseButton1 or input.KeyCode == Enum.KeyCode.ButtonR2 or input.UserInputType == Enum.UserInputType.Touch then
		if isReloading then
			if not mouseDestrancado then
				pcall(function() AmmoUIManager.shakeAmmoUI(false) end)
			end
			return
		end
		if mouseDestrancado then return end
		isMouseDown = true
		if ammo <= 0 then
			if reserveAmmo <= 0 then
				pcall(function() AmmoUIManager.shakeAmmoUI(true) end)
			else
				pcall(function() AmmoUIManager.shakeAmmoUI(false) end)
			end
		end
		task.spawn(loopTiro)
	end
end)

UIS.InputEnded:Connect(function(input)
	if input.UserInputType == Enum.UserInputType.MouseButton1 or input.KeyCode == Enum.KeyCode.ButtonR2 or input.UserInputType == Enum.UserInputType.Touch then
		isMouseDown = false
	end
end)

tool.Equipped:Connect(function()
	podeAtirar = false
	character = player.Character or player.CharacterAdded:Wait()
	humanoid = character:WaitForChild("Humanoid")
	animator = humanoid:WaitForChild("Animator")
	originalFOV = camera.FieldOfView 
	isEquipped = true
	isReloading = false
	isTransicaoRecarga = false
	thetaAtivo = 0
	mouseDestrancado = false

	task.spawn(function() AmmoUIManager.showAmmoUI(ammo, maxAmmo, reserveAmmo, maxReserveAmmo, function() return isEquipped end) end)

	for _, track in ipairs(animator:GetPlayingAnimationTracks()) do
		track:Stop(0)
	end

	loadAnims()
	solicitarMotor6D()

	if character and humanoid.Health > 0 then
		local cameraCFrame = camera.CFrame
		local theta = math.asin(cameraCFrame.LookVector.Y)
		local minRad = math.rad(-LIMITES.MaxDescer)
		local maxRad = math.rad(LIMITES.MaxSubir)
		local thetaLimitado = math.clamp(theta, minRad, maxRad)

		if humanoid.RigType == Enum.HumanoidRigType.R6 then
			if rightShoulder and originalRightC0 then rightShoulder.C0 = originalRightC0 * CFrame.Angles(0, 0, thetaLimitado) end
			if leftShoulder and originalLeftC0 then leftShoulder.C0 = originalLeftC0 * CFrame.Angles(0, 0, -thetaLimitado) end
			if neck and originalNeckC0 then neck.C0 = originalNeckC0 * CFrame.Angles(-thetaLimitado, 0, 0) end
		else
			if rightShoulder and originalRightC0 then rightShoulder.C0 = originalRightC0 * CFrame.Angles(-thetaLimitado, 0, 0) end
			if leftShoulder and originalLeftC0 then leftShoulder.C0 = originalLeftC0 * CFrame.Angles(-thetaLimitado, 0, 0) end
			if neck and originalNeckC0 then neck.C0 = originalNeckC0 * CFrame.Angles(-thetaLimitado, 0, 0) end
		end
	end

	particleEmitters, beamsEfeito = EfeitosParticulas.Inicializar(tool)

	if idleTrack then idleTrack:Play(0) end

	task.wait(0.05)
	if isEquipped then
		podeAtirar = true
	end

	if diedConn then diedConn:Disconnect() end
	diedConn = humanoid.Died:Connect(function()
		isEquipped = false
		podeAtirar = false
		isMouseDown = false
		isReloading = false
		isTransicaoRecarga = false
		thetaAtivo = 0
		mouseDestrancado = false
		AmmoUIManager.hideAmmoUI()
		UIS.MouseBehavior = Enum.MouseBehavior.Default
		camera.FieldOfView = originalFOV

		if updateConnection then
			updateConnection:Disconnect()
			updateConnection = nil
		end

		InclinacaoBracoEvent:FireServer(0)

		if rightShoulder and originalRightC0 then rightShoulder.C0 = originalRightC0 end
		if leftShoulder and originalLeftC0 then leftShoulder.C0 = originalLeftC0 end
		if neck and originalNeckC0 then neck.C0 = originalNeckC0 end

		stopAllTracks()
	end)

	if ammo <= 0 and not isReloading and not mouseDestrancado then
		task.spawn(recarregar)
	end
end)

tool.Unequipped:Connect(function()
	isEquipped = false
	podeAtirar = false
	isMouseDown = false
	mouseDestrancado = false
	AmmoUIManager.hideAmmoUI()
	UIS.MouseBehavior = Enum.MouseBehavior.Default

	if isReloading then
		ammo = 0
		isReloading = false
	end
	isTransicaoRecarga = false
	thetaAtivo = 0
	camera.FieldOfView = originalFOV 

	if updateConnection then 
		updateConnection:Disconnect() 
		updateConnection = nil
	end

	if diedConn then
		diedConn:Disconnect()
		diedConn = nil
	end

	local rightArm = character:FindFirstChild("Right Arm") or character:FindFirstChild("RightHand")
	if rightArm then

		local m6d = rightArm:FindFirstChild("ToolGrip6D")
		if m6d and m6d.Part1 == handle then 
			m6d:Destroy() 
		end
		local holder = rightArm:FindFirstChild("Holder")
		if holder then holder:Destroy() end
	end

	local torso = character:FindFirstChild("Torso") or character:FindFirstChild("UpperTorso")
	if torso then
		local oldMochilaGrip = torso:FindFirstChild("MochilaGrip6D")
		if oldMochilaGrip then oldMochilaGrip:Destroy() end

		rightShoulder = torso:FindFirstChild("Right Shoulder") or (character:FindFirstChild("RightUpperArm") and character.RightUpperArm:FindFirstChild("RightShoulder"))
		leftShoulder = torso:FindFirstChild("Left Shoulder") or (character:FindFirstChild("LeftUpperArm") and character.LeftUpperArm:FindFirstChild("LeftShoulder"))
	end

	local head = character:FindFirstChild("Head")
	if head then
		neck = head:FindFirstChild("Neck") or (torso and torso:FindFirstChild("Neck"))
	end

	InclinacaoBracoEvent:FireServer(0)

	if rightShoulder and originalRightC0 then rightShoulder.C0 = originalRightC0 end
	if leftShoulder and originalLeftC0 then leftShoulder.C0 = originalLeftC0 end
	if neck and originalNeckC0 then neck.C0 = originalNeckC0 end

	if animator then
		for _, track in ipairs(animator:GetPlayingAnimationTracks()) do
			if track.Animation and (track.Animation.AnimationId == animIdle.AnimationId 
				or track.Animation.AnimationId == animShoot.AnimationId 
				or track.Animation.AnimationId == animReload.AnimationId) then
				track:Stop(0)
			end
		end
	end
	stopAllTracks()
end)

if idleTrack then idleTrack:Stop(0) end
if reloadTrack then reloadTrack:Stop(0) end
if shootTrack then shootTrack:Stop(0) end
